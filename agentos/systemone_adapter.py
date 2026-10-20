"""SystemOne backend adapter layer (R3.2A): real local decision backends behind the typed contract.

  SystemOneRequest -> AdapterBackend -> DecisionRuntime (JSON in/out) -> validated Answer

Nothing here knows about any particular model. A runtime only has to answer one compact JSON
request with one JSON reply; this module owns everything that makes that safe:

- The payload is built from an allowlist of operational fields (task type, risk, capability ids,
  option ids, small scalar state), redacted and size-capped. No repo context, no prose, no secrets.
- The reply is NEVER authority. It is parsed field by field; only a `choice` that is one of the
  request's options, plus an optional raw confidence number, survive. Anything else is dropped.
- Every failure (timeout, crash, unavailable, malformed, unknown option, missing answer, oversized
  state, unsupported question) becomes an ESCALATION with a specific reason code. Nothing raises
  into the router, and system_one() still re-validates the response.
- The subprocess runtime runs the model in a separate process with a scrubbed environment (no
  inherited secrets; not an OS/network sandbox), a hard per-request deadline (the process is killed on expiry), and a
  failure cool-down so a broken backend cannot add its timeout to every route.

Confidence stays `kind="raw"`: this layer never produces a calibrated confidence.
"""
from __future__ import annotations

import atexit
import json
import math
import os
import re
import select
import signal
import subprocess
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from . import events
from .systemone import (REASON_CODES, Answer, Confidence, SystemOneRequest, SystemOneResponse)

PROTOCOL_VERSION = 1
MAX_PAYLOAD_BYTES = 4096
MAX_REPLY_BYTES = 8192
_OPTION_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
# Closed set of reasons this layer can escalate with (a subset of systemone.REASON_CODES).
ESCALATION_REASONS = ("backend-timeout", "backend-unavailable", "backend-error", "malformed-output",
                      "ineligible-choice", "unanswered-question", "unsupported-question", "state-too-large",
                      "backend-abstained")
# Per-option metadata (R3.2C): allowlisted fields only, produced from authoritative config/registry by
# agentos/systemone_options.py. Anything else is rejected, never forwarded.
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
OPTION_FIELDS = {"roles": "list", "missing": "list", "access": "token", "cost": "token", "locality": "token",
                 "latency": "token", "status": "token", "interactive": "bool"}
MAX_INFO_LIST = 8
assert set(ESCALATION_REASONS) <= set(REASON_CODES)


class AdapterReject(Exception):
    """A request/reply the adapter refuses; `reason` is one of ESCALATION_REASONS."""

    def __init__(self, reason: str, detail: str = ""):
        assert reason in ESCALATION_REASONS, reason
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


class DecisionRuntime(Protocol):
    """Anything that can answer one compact JSON request. Raises AdapterReject on failure."""
    name: str

    def ask(self, payload: dict, timeout: float) -> object: ...

    def close(self) -> None: ...


# ------------------------------------------------------------ option metadata
def sanitize_option_info(option_info, options: list[str]) -> dict:
    """Validated, size-capped metadata for exactly the offered options.

    Entries for ids outside `options` are dropped (metadata can never introduce an option). Unknown
    fields, wrong types or malformed values are rejected, and so is any list longer than MAX_INFO_LIST
    (truncating e.g. `missing` capabilities could hide a hard constraint). Raises AdapterReject."""
    if not option_info:
        return {}
    if not isinstance(option_info, Mapping):
        raise AdapterReject("unsupported-question", "option_info is not a mapping")
    out = {}
    for opt in options:
        info = option_info.get(opt)
        if not info:
            continue
        if not isinstance(info, Mapping):
            raise AdapterReject("unsupported-question", f"option_info[{opt}] is not a mapping")
        clean = {}
        for key, value in sorted(info.items(), key=lambda kv: str(kv[0])):
            kind = OPTION_FIELDS.get(key)
            if kind is None:
                raise AdapterReject("unsupported-question", f"unknown option_info field {str(key)[:32]!r}")
            texts = [value] if isinstance(value, str) else [v for v in value if isinstance(v, str)] \
                if isinstance(value, (list, tuple)) else []
            if any(events._SECRET.search(t) for t in texts):        # defense in depth: never forward secret-looking text
                raise AdapterReject("unsupported-question", f"option_info[{opt}].{key} looks like a secret")
            if kind == "bool":
                ok = isinstance(value, bool)
            elif kind == "token":
                ok = isinstance(value, str) and bool(_TOKEN.fullmatch(value))
            else:
                if isinstance(value, (list, tuple)) and len(value) > MAX_INFO_LIST:
                    raise AdapterReject("state-too-large", f"option_info[{opt}].{key} has too many items")
                ok = isinstance(value, (list, tuple)) and all(isinstance(v, str) and _TOKEN.fullmatch(v) for v in value)
                value = list(value) if ok else value
            if not ok:
                raise AdapterReject("unsupported-question", f"option_info[{opt}].{key} has an invalid value")
            clean[key] = value
        if clean:
            out[opt] = clean
    return out


# ------------------------------------------------------------ payload (what a model is shown)
def _scalar(value):
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return events._clean(value)                     # redacts secret-looking text, truncates to 200


def build_payload(request: SystemOneRequest, question) -> dict:
    """Compact operational state for one `choose` question. Raises AdapterReject."""
    if question.kind != "choose":
        raise AdapterReject("unsupported-question", question.kind)
    options = [o for o in (question.options or request.eligible_options) if o in request.eligible_options]
    if not options:
        raise AdapterReject("unanswered-question", "no options")
    if len(set(options)) != len(options) or not all(_OPTION_ID.fullmatch(str(o)) for o in options):
        raise AdapterReject("unsupported-question", "option ids must be unique simple identifiers")
    state = {
        "task_type": _scalar(request.task_type), "risk": _scalar(request.risk),
        "required_capabilities": sorted(_scalar(c) for c in request.required_capabilities),
        "cost_profile": _scalar(request.cost_profile),
        "context": {str(k)[:64]: _scalar(v) for k, v in sorted(request.state.items(), key=lambda kv: str(kv[0]))},
        "resources": {str(k)[:64]: _scalar(v) for k, v in sorted(request.resource_state.items(),
                                                                 key=lambda kv: str(kv[0]))},
    }
    state = {k: v for k, v in state.items() if v not in (None, [], {})}
    payload = {"v": PROTOCOL_VERSION,
               "question": {"id": str(question.id), "kind": "choose", "prompt": _scalar(question.prompt or "")},
               "options": options, "state": state}
    info = sanitize_option_info(request.option_info, options)
    if info:                                   # additive v1 field: workers that predate it ignore it
        payload["option_info"] = info
    if request.allow_abstain:
        payload["allow_abstain"] = True
    if len(json.dumps(payload, separators=(",", ":")).encode()) > MAX_PAYLOAD_BYTES:
        raise AdapterReject("state-too-large")
    return payload


# ------------------------------------------------------------ reply (what is trusted from a model)
def parse_reply(reply: object, payload: dict) -> Answer:
    """Validate one runtime reply against the payload that produced it. Raises AdapterReject."""
    if not isinstance(reply, dict):
        raise AdapterReject("malformed-output", "reply is not an object")
    if reply.get("v") != PROTOCOL_VERSION or reply.get("id") != payload["question"]["id"]:
        raise AdapterReject("malformed-output", "protocol version or question id mismatch")
    if reply.get("abstain") is True:
        if reply.get("choice") is not None or not payload.get("allow_abstain"):
            raise AdapterReject("malformed-output", "abstain not allowed or combined with a choice")
        raise AdapterReject("backend-abstained")             # an escalation, never a choice
    if "error" in reply and reply.get("choice") is None:
        raise AdapterReject("backend-error", "runtime reported an error")
    choice = reply.get("choice")
    if choice is None:
        raise AdapterReject("unanswered-question")
    if not isinstance(choice, str):
        raise AdapterReject("malformed-output", "choice is not a string")
    if choice not in payload["options"]:
        raise AdapterReject("ineligible-choice")
    conf = reply.get("confidence")
    if conf is None:
        confidence = Confidence()
    elif isinstance(conf, bool) or not isinstance(conf, (int, float)) or not math.isfinite(conf) \
            or not 0.0 <= conf <= 1.0:
        raise AdapterReject("malformed-output", "confidence is not a number in [0, 1]")
    else:
        confidence = Confidence(float(conf), "raw")           # never calibrated here
    code = reply.get("reason_code")
    if not (isinstance(code, str) and code in REASON_CODES):
        code = "backend-choice"                               # free-form model text is never kept
    return Answer(payload["question"]["id"], choice, confidence, code)


# ------------------------------------------------------------ backend
class AdapterBackend:
    """A SystemOneBackend that delegates each `choose` question to a DecisionRuntime."""

    def __init__(self, name: str, runtime: DecisionRuntime, timeout: float = 2.0):
        self.name, self.runtime, self.timeout = name, runtime, float(timeout)

    def _escalate(self, reason: str) -> SystemOneResponse:
        return SystemOneResponse((), True, reason, self.name)

    def decide(self, request: SystemOneRequest) -> SystemOneResponse:
        try:
            answers = []
            for q in request.questions:
                payload = build_payload(request, q)
                reply = self.runtime.ask(payload, self.timeout)
                answers.append(parse_reply(reply, payload))
            return SystemOneResponse(tuple(answers), False, "backend-choice", self.name)
        except AdapterReject as exc:
            return self._escalate(exc.reason)
        except Exception:                                      # never raise into the router
            return self._escalate("backend-error")

    def close(self) -> None:
        self.runtime.close()


# ------------------------------------------------------------ subprocess JSON-lines runtime
def scrubbed_env() -> dict:
    """Environment for a model process: built from scratch, never a copy of os.environ, so no
    token or credential is inherited. HF_HUB_OFFLINE=1 is a convention for libraries that honour it, NOT
    an OS/network sandbox: the child runs with the user's privileges and HOME. Weights must already be on disk."""
    return {"PATH": "/usr/bin:/bin", "HOME": os.path.expanduser("~"), "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}


def _kill_group(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            break
        try:
            proc.wait(timeout=1.0)
            break
        except subprocess.TimeoutExpired:
            continue


class SubprocessJsonRuntime:
    """Long-lived worker process speaking one JSON object per line over stdin/stdout.

    The worker prints `{"ready": true, ...}` once its model is loaded, then answers each request
    line with exactly one reply line. A request that exceeds its deadline kills the process group
    (a late reply could otherwise be mistaken for the next answer); after any failure the runtime
    refuses calls for `cooldown` seconds, then restarts lazily."""

    def __init__(self, argv: list[str], *, name: str = "subprocess", env: dict | None = None,
                 cwd: str | os.PathLike | None = None, startup_timeout: float = 60.0, cooldown: float = 30.0):
        self.argv, self.name, self.env = list(argv), name, env if env is not None else scrubbed_env()
        self.cwd, self.startup_timeout, self.cooldown = cwd, float(startup_timeout), float(cooldown)
        self.info: dict = {}                       # the worker's ready message (versions, no secrets)
        self.startup_seconds: float | None = None
        self._proc: subprocess.Popen | None = None
        self._buf = b""
        self._down_until = 0.0
        self._lock = threading.Lock()
        atexit.register(self.close)

    # -- lifecycle
    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc and self._proc.poll() is None else None

    def rss_kib(self) -> int | None:
        if self.pid is None:
            return None
        try:
            out = subprocess.run(["ps", "-o", "rss=", "-p", str(self.pid)], capture_output=True, text=True,
                                 timeout=2).stdout.strip()
            return int(out) if out else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    def _fail(self, reason: str, detail: str = "") -> AdapterReject:
        self._stop()
        self._down_until = time.monotonic() + self.cooldown
        return AdapterReject(reason, detail)

    def _stop(self) -> None:
        proc, self._proc, self._buf = self._proc, None, b""
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            _kill_group(proc)

    def close(self) -> None:
        with self._lock:
            self._stop()

    def _read_line(self, deadline: float) -> bytes:
        fd = self._proc.stdout.fileno()
        while b"\n" not in self._buf:
            if len(self._buf) > MAX_REPLY_BYTES:
                raise AdapterReject("malformed-output", "reply too large")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            if not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError
            chunk = os.read(fd, 4096)
            if not chunk:
                raise EOFError
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        if len(line) > MAX_REPLY_BYTES:
            raise AdapterReject("malformed-output", "reply too large")
        return line

    def _start(self) -> None:
        t0 = time.monotonic()
        try:
            self._proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, env=self.env, cwd=self.cwd,
                                          start_new_session=True, bufsize=0)
        except (OSError, ValueError) as exc:
            raise self._fail("backend-unavailable", type(exc).__name__) from None
        try:
            ready = json.loads(self._read_line(t0 + self.startup_timeout))
        except TimeoutError:
            raise self._fail("backend-timeout", "startup") from None
        except (EOFError, OSError):
            raise self._fail("backend-unavailable", "worker exited during startup") from None
        except AdapterReject as exc:
            raise self._fail(exc.reason, exc.detail) from None
        except ValueError:
            raise self._fail("malformed-output", "startup message") from None
        if not (isinstance(ready, dict) and ready.get("ready") is True):
            raise self._fail("backend-unavailable", "worker did not report ready")
        runtime = ready.get("runtime")
        self.info = {str(k)[:32]: str(v)[:64] for k, v in runtime.items()} if isinstance(runtime, dict) else {}
        self.startup_seconds = round(time.monotonic() - t0, 3)

    # -- request/response
    def ask(self, payload: dict, timeout: float) -> object:
        with self._lock:
            if time.monotonic() < self._down_until:
                raise AdapterReject("backend-unavailable", "cooling down after a failure")
            if self._proc is None or self._proc.poll() is not None:
                self._stop()
                self._start()
            deadline = time.monotonic() + timeout
            try:
                self._proc.stdin.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
                line = self._read_line(deadline)
            except TimeoutError:
                raise self._fail("backend-timeout") from None
            except (EOFError, BrokenPipeError, OSError):
                raise self._fail("backend-unavailable", "worker exited") from None
            except AdapterReject as exc:
                raise self._fail(exc.reason, exc.detail) from None
            try:
                return json.loads(line)
            except ValueError:
                raise self._fail("malformed-output", "reply is not JSON") from None


# ------------------------------------------------------------ configured backends
_CACHE: dict[str, AdapterBackend] = {}


def definitions(cfg) -> dict:
    return ((getattr(cfg, "data", {}) or {}).get("systemone") or {}).get("backends") or {}


def _expand(arg: str, cfg, conf: dict) -> str:
    runtime = (Path(cfg.root) / conf.get("runtime_dir", "state/runtime")).resolve()
    return os.path.expanduser(str(arg).replace("{repo}", str(Path(cfg.root).resolve()))
                              .replace("{runtime}", str(runtime)))


def _build_subprocess_json(name: str, conf: dict, cfg) -> AdapterBackend:
    runtime = SubprocessJsonRuntime(
        [_expand(a, cfg, conf) for a in conf["argv"]], name=name, cwd=str(Path(cfg.root).resolve()),
        startup_timeout=conf.get("startup_timeout_seconds", 60.0), cooldown=conf.get("cooldown_seconds", 30.0))
    return AdapterBackend(name, runtime, timeout=conf.get("timeout_seconds", 2.0))


ADAPTERS = {"subprocess_json": _build_subprocess_json}


def validate_definition(name: str, conf: object) -> list[str]:
    """Structural errors for one `config/systemone.yaml` backend definition (empty == valid)."""
    where = f"systemone.backends.{name}"
    if not isinstance(conf, dict):
        return [f"{where}: must be a mapping"]
    errors = []
    if conf.get("adapter") not in ADAPTERS:
        errors.append(f"{where}: adapter must be one of {sorted(ADAPTERS)}")
    argv = conf.get("argv")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)):
        errors.append(f"{where}: argv must be a non-empty list of strings")
    for key in ("timeout_seconds", "startup_timeout_seconds", "cooldown_seconds"):
        v = conf.get(key)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0
                              or (key != "cooldown_seconds" and v == 0)):
            errors.append(f"{where}: {key} must be a positive number")
    return errors


def backend_for(name: str, cfg) -> AdapterBackend:
    """The configured adapter backend `name` (cached per process so a loaded model stays warm)."""
    conf = definitions(cfg).get(name)
    if conf is None:
        raise ValueError(f"no SystemOne backend definition {name!r} in config/systemone.yaml")
    errors = validate_definition(name, conf)
    if errors:
        raise ValueError("; ".join(errors))
    key = f"{Path(cfg.root).resolve()}::{name}::{json.dumps(conf, sort_keys=True)}"
    if key not in _CACHE:
        _CACHE[key] = ADAPTERS[conf["adapter"]](name, conf, cfg)
    return _CACHE[key]


def close_all() -> None:
    for backend in list(_CACHE.values()):
        backend.close()
    _CACHE.clear()
