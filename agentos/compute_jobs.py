"""Typed job contract for future compute nodes (CN-1). Mac side only: no network client ships here.

Mac/Hermes keeps authority over intent, eligibility, data sensitivity, authorization, approval, routing, cloud
escalation and durable audit. A node may report resources, accept/reject an AUTHORIZED job, queue, load/unload
a runtime, execute the approved offering and return a result - nothing else. So:

- the request names the approved node AND offering; a response for any other node/offering/model revision is
  INVALID_RESPONSE, never accepted;
- eligibility (compute.evaluate) is decided from protected config before anything is sent, and an offline,
  disabled, unauthorized or over-sensitive case never reaches a client;
- every operational failure becomes a FAILED/CANCELLED JobResult with a closed-vocabulary error code; nothing
  raises into callers and no failure path can produce a completed result;
- states move only along TRANSITIONS; terminal states are final.

Idempotency (documented semantics): the (idempotency_key, canonical request hash) pair is recorded when a job is
first accepted by the ledger. Same key + same request  -> the original JobResult/record is returned unchanged
(replayed=True, nothing re-sent). Same key + a different request -> DUPLICATE_REQUEST, nothing sent.
A request refused BEFORE anything reached a client (policy, disabled/offline node, capability unavailable) is
not recorded: its key may be retried. Once a request was sent, its outcome is final for that key.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from . import compute, events
from .config import Config

ERROR_CODES = ("NODE_UNAVAILABLE", "CAPABILITY_UNAVAILABLE", "NOT_AUTHORIZED", "RESOURCE_BUSY",
               "RESOURCE_EXHAUSTED", "TIMEOUT", "BACKEND_FAILURE", "INVALID_RESPONSE", "CANCELLED",
               "DUPLICATE_REQUEST")
RETRYABLE = {"NODE_UNAVAILABLE", "RESOURCE_BUSY", "RESOURCE_EXHAUSTED", "TIMEOUT"}


class Status(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {Status.COMPLETED, Status.FAILED, Status.CANCELLED}
TRANSITIONS = {
    Status.QUEUED: {Status.RUNNING, Status.FAILED, Status.CANCELLED},
    Status.RUNNING: {Status.COMPLETED, Status.FAILED, Status.CANCELLED},
    Status.COMPLETED: set(), Status.FAILED: set(), Status.CANCELLED: set(),
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
_REF = re.compile(r"(sha256:[0-9a-f]{64}|artifact:[A-Za-z0-9_.-]{1,64}|secondbrain:[A-Za-z0-9_./-]{1,200})")


class ComputeError(Exception):
    """A contract failure with a closed-vocabulary code."""

    def __init__(self, code: str, detail: str = ""):
        assert code in ERROR_CODES, code
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


class InvalidTransition(Exception):
    pass


class RequestInvalid(ValueError):
    """The Mac-side request itself is malformed (a caller bug, raised before anything else happens)."""


# ------------------------------------------------------------------ request / result types
@dataclass(frozen=True)
class ArtifactRef:
    ref: str                       # sha256:<hex> | artifact:<id> | secondbrain:<relative path>; never a URL
    kind: str = "input"


@dataclass(frozen=True)
class ResourceRequirements:
    vram_mb: int = 0
    ram_mb: int = 0
    exclusive_gpu: bool = False


@dataclass(frozen=True)
class AuditRef:
    task_id: str
    run_id: str | None = None
    approval_ref: str | None = None
    requested_by: str = "hermes"


@dataclass(frozen=True)
class JobRequest:
    job_id: str
    idempotency_key: str
    capability: str                # capability type id (config/compute.yaml capability_types)
    offering: str                  # approved offering id; names the pinned model/revision
    approved_node: str             # chosen by Mac policy, not by the node
    operation: str
    audit: AuditRef
    inputs: tuple = ()
    params: Mapping = field(default_factory=dict)
    deadline_seconds: int = 60
    resources: ResourceRequirements = ResourceRequirements()
    data_class: str = "public"

    def payload(self) -> dict:
        """The exact JSON body sent to POST /v1/jobs. Credentials and policy never travel in it."""
        return {"v": 1, "job_id": self.job_id, "idempotency_key": self.idempotency_key,
                "capability": self.capability, "offering": self.offering, "operation": self.operation,
                "inputs": [{"ref": i.ref, "kind": i.kind} for i in self.inputs], "params": dict(self.params),
                "deadline_seconds": self.deadline_seconds,
                "resources": {"vram_mb": self.resources.vram_mb, "ram_mb": self.resources.ram_mb,
                              "exclusive_gpu": self.resources.exclusive_gpu},
                "audit": {"task_id": self.audit.task_id, "run_id": self.audit.run_id}}

    def fingerprint(self) -> str:
        body = {**self.payload(), "approved_node": self.approved_node, "data_class": self.data_class}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class ResourceUsage:
    wall_ms: int | None = None
    vram_peak_mb: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


@dataclass(frozen=True)
class JobError:
    code: str
    message: str = ""
    retryable: bool = False


@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: Status
    node: str
    offering: str
    capability: str
    result: Mapping | None = None
    usage: ResourceUsage = ResourceUsage()
    error: JobError | None = None
    provenance: Mapping = field(default_factory=dict)      # model id/revision/runtime as REPORTED, for audit
    replayed: bool = False

    @property
    def ok(self) -> bool:
        return self.status is Status.COMPLETED and self.error is None and self.result is not None

    def to_dict(self) -> dict:
        return {"job_id": self.job_id, "status": self.status.value, "node": self.node, "offering": self.offering,
                "capability": self.capability, "result": self.result, "usage": vars(self.usage),
                "error": vars(self.error) if self.error else None, "provenance": dict(self.provenance),
                "replayed": self.replayed}


def validate_request(cfg: Config, r: JobRequest) -> None:
    """Structural validation of the Mac-side request. Raises RequestInvalid."""
    lim = compute.limits(cfg)
    types = (compute.section(cfg).get("capability_types") or {})
    for name in ("job_id", "idempotency_key"):
        if not (isinstance(getattr(r, name), str) and _ID.fullmatch(getattr(r, name))):
            raise RequestInvalid(f"{name} must match {_ID.pattern}")
    if r.capability not in types:
        raise RequestInvalid(f"unknown capability type {r.capability!r}")
    if r.operation not in (types[r.capability].get("operations") or []):
        raise RequestInvalid(f"operation {r.operation!r} not defined for {r.capability}")
    if not (isinstance(r.audit, AuditRef) and r.audit.task_id):
        raise RequestInvalid("audit.task_id is required (every job is traceable to a Mac task)")
    if isinstance(r.deadline_seconds, bool) or not isinstance(r.deadline_seconds, int) \
            or not 0 < r.deadline_seconds <= lim["max_deadline_seconds"]:
        raise RequestInvalid(f"deadline_seconds must be 1..{lim['max_deadline_seconds']}")
    if len(r.inputs) > lim["max_inputs"] or not all(isinstance(i, ArtifactRef) and _REF.fullmatch(i.ref)
                                                    and ".." not in i.ref for i in r.inputs):
        raise RequestInvalid("inputs must be artifact references (sha256:/artifact:/secondbrain:), never URLs")
    try:
        size = len(json.dumps(dict(r.params), sort_keys=True).encode())
    except (TypeError, ValueError):
        raise RequestInvalid("params must be JSON-serialisable") from None
    if size > lim["max_params_bytes"]:
        raise RequestInvalid("params too large")
    rs = r.resources
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (rs.vram_mb, rs.ram_mb)):
        raise RequestInvalid("resources must be non-negative integers")
    if r.data_class not in compute.data_classes(cfg):
        raise RequestInvalid(f"unknown data_class {r.data_class!r}")


# ------------------------------------------------------------------ response parsing
_RESPONSE_KEYS = {"v", "job_id", "status", "node", "offering", "capability", "result", "usage", "error",
                  "provenance"}
_USAGE_KEYS = {"wall_ms", "vram_peak_mb", "tokens_in", "tokens_out"}


def parse_response(raw: object, req: JobRequest, cfg: Config) -> JobResult:
    """Validate one node response against the request that produced it. Raises ComputeError(INVALID_RESPONSE)."""
    bad = lambda why: ComputeError("INVALID_RESPONSE", why)       # noqa: E731
    if not isinstance(raw, dict) or set(raw) - _RESPONSE_KEYS:
        raise bad("not an object with the contract's fields")
    if raw.get("v") != 1 or raw.get("job_id") != req.job_id:
        raise bad("protocol version or job id mismatch")
    try:
        status = Status(raw.get("status"))
    except ValueError:
        raise bad("unknown status") from None
    if raw.get("node") != req.approved_node or raw.get("offering") != req.offering \
            or raw.get("capability") != req.capability:
        raise bad("response names a different node/offering/capability than the approved one")
    off = compute.offerings(cfg).get(req.offering) or {}
    prov = raw.get("provenance") or {}
    pinned = (off.get("model") or {})
    if not isinstance(prov, dict) or prov.get("model_id") != pinned.get("id") \
            or prov.get("model_revision") != pinned.get("revision"):
        raise bad("provenance does not match the pinned model id/revision")
    u = raw.get("usage") or {}
    if not isinstance(u, dict) or set(u) - _USAGE_KEYS \
            or any(v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0) for v in u.values()):
        raise bad("malformed usage")
    err = raw.get("error")
    jerr = None
    if err is not None:
        if not isinstance(err, dict) or set(err) - {"code", "message"} or err.get("code") not in ERROR_CODES:
            raise bad("malformed error")
        jerr = JobError(err["code"], str(events._clean(str(err.get("message") or "")))[:200],
                        err["code"] in RETRYABLE)
    result = raw.get("result")
    if status is Status.COMPLETED:
        if not isinstance(result, dict) or jerr is not None:
            raise bad("completed requires a structured result and no error")
    else:
        if result is not None:
            raise bad(f"{status.value} must not carry a result")
        if status is Status.FAILED and jerr is None:
            raise bad("failed requires an error")
        if status is Status.CANCELLED and jerr is not None and jerr.code != "CANCELLED":
            raise bad("cancelled may only carry a CANCELLED error")
        if status in (Status.QUEUED, Status.RUNNING) and jerr is not None:
            raise bad("non-terminal state must not carry an error")
    return JobResult(req.job_id, status, req.approved_node, req.offering, req.capability, result,
                     ResourceUsage(**{k: u.get(k) for k in _USAGE_KEYS}), jerr,
                     {str(k)[:32]: events._clean(v) for k, v in list(prov.items())[:8]})


# ------------------------------------------------------------------ client protocol and ledger
class NodeClient(Protocol):
    """What CN-2 must implement over a private authenticated transport. Each call returns decoded JSON or
    raises ComputeError (NODE_UNAVAILABLE / TIMEOUT / BACKEND_FAILURE ...)."""

    def health(self) -> dict: ...
    def capabilities(self) -> dict: ...
    def resources(self) -> dict: ...
    def submit(self, payload: dict) -> dict: ...
    def get(self, job_id: str) -> dict: ...
    def cancel(self, job_id: str) -> dict: ...


class OfflineClient:
    """The shipped default: there is no transport, so every call is NODE_UNAVAILABLE."""

    def _down(self, *_a, **_k):
        raise ComputeError("NODE_UNAVAILABLE", "no compute node client configured")

    health = capabilities = resources = submit = get = cancel = _down


@dataclass
class JobRecord:
    request: JobRequest
    fingerprint: str
    status: Status = Status.QUEUED
    sent: bool = False                  # True once a byte was handed to a client
    result: JobResult | None = None
    history: list = field(default_factory=lambda: [Status.QUEUED])

    def advance(self, new: Status) -> None:
        if new == self.status:
            return
        if new not in TRANSITIONS[self.status]:
            raise InvalidTransition(f"{self.status.value} -> {new.value}")
        self.status = new
        self.history.append(new)


class JobLedger:
    """In-memory idempotency/state ledger (durable Mac audit is an CN-2 dependency)."""

    def __init__(self):
        self._by_key: dict[str, JobRecord] = {}

    def get(self, key: str) -> JobRecord | None:
        return self._by_key.get(key)

    def discard(self, key: str) -> None:
        self._by_key.pop(key, None)

    def admit(self, req: JobRequest) -> tuple[JobRecord, bool]:
        """(record, is_new). Raises ComputeError(DUPLICATE_REQUEST) for a reused key with a different request."""
        fp = req.fingerprint()
        rec = self._by_key.get(req.idempotency_key)
        if rec is None:
            rec = self._by_key[req.idempotency_key] = JobRecord(req, fp)
            return rec, True
        if rec.fingerprint != fp:
            raise ComputeError("DUPLICATE_REQUEST", "idempotency key already used by a different request")
        return rec, False


# ------------------------------------------------------------------ the orchestration entry point
def _fail(req: JobRequest, code: str, detail: str = "", status: Status = Status.FAILED) -> JobResult:
    return JobResult(req.job_id, status, req.approved_node, req.offering, req.capability, None,
                     error=JobError(code, str(events._clean(detail))[:200], code in RETRYABLE))


def run_job(cfg: Config, req: JobRequest, client: NodeClient | None = None, ledger: JobLedger | None = None, *,
            clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
            poll_interval: float = 0.5) -> JobResult:
    """Authorize, send, poll and validate one job. Returns a JobResult; operational failures are results, not
    exceptions (RequestInvalid is the one exception: a malformed request is a caller bug)."""
    client = client or OfflineClient()
    ledger = ledger if ledger is not None else JobLedger()
    validate_request(cfg, req)
    try:
        rec, new = ledger.admit(req)
    except ComputeError as exc:
        return _fail(req, exc.code, exc.detail)
    if not new:                                    # idempotent replay: never re-send
        base = rec.result or JobResult(req.job_id, rec.status, req.approved_node, req.offering, req.capability)
        return JobResult(**{**vars(base), "replayed": True})
    result = _execute(cfg, req, client, rec, clock, sleep, poll_interval)
    rec.result = result
    if not rec.sent:                               # refused before anything was sent: the key stays reusable
        ledger.discard(req.idempotency_key)
    return result


def _execute(cfg, req, client, rec, clock, sleep, poll_interval) -> JobResult:
    off = compute.offerings(cfg).get(req.offering)
    # -- policy: decided from protected config only, before any byte reaches a node
    if not isinstance(off, dict) or off.get("node") != req.approved_node or off.get("capability") != req.capability \
            or req.operation not in (off.get("operations") or []):
        return _terminal(rec, _fail(req, "NOT_AUTHORIZED", "offering/node/capability/operation not approved"))
    auth = compute.authorization_for(cfg, req.offering)
    classes = compute.data_classes(cfg)
    if auth is None or classes.index(req.data_class) > classes.index(auth["max_data_class"]):
        return _terminal(rec, _fail(req, "NOT_AUTHORIZED", "no authorization covering this offering and data class"))
    if not compute.node_enabled(cfg, req.approved_node):
        return _terminal(rec, _fail(req, "NODE_UNAVAILABLE", "node not enabled for compute"))
    # -- discovery (untrusted): may only make the job less eligible
    try:
        health = client.health()
        adv = client.capabilities()
    except ComputeError as exc:
        return _terminal(rec, _fail(req, exc.code, exc.detail))
    except Exception:
        return _terminal(rec, _fail(req, "NODE_UNAVAILABLE", "node unreachable"))
    elig = compute.evaluate(cfg, req.offering, advertised=adv, node_reachable=True,
                            node_healthy=isinstance(health, dict) and health.get("ok") is True)
    if not (elig.installed and elig.healthy):
        return _terminal(rec, _fail(req, "CAPABILITY_UNAVAILABLE", "; ".join(elig.reasons)))
    if not elig.active:
        return _terminal(rec, _fail(req, "NOT_AUTHORIZED", "; ".join(elig.reasons)))
    # -- execute
    deadline = clock() + req.deadline_seconds
    rec.sent = True
    try:
        res = parse_response(client.submit(req.payload()), req, cfg)
        rec = _apply(rec, res)
        while rec.status not in TERMINAL:
            if clock() >= deadline:
                _best_effort_cancel(client, req.job_id)
                return _terminal(rec, _fail(req, "TIMEOUT", "deadline exceeded"))
            sleep(poll_interval)
            res = parse_response(client.get(req.job_id), req, cfg)
            rec = _apply(rec, res)
    except ComputeError as exc:
        if exc.code == "INVALID_RESPONSE":
            _best_effort_cancel(client, req.job_id)
        return _terminal(rec, _fail(req, exc.code, exc.detail))
    except InvalidTransition as exc:
        _best_effort_cancel(client, req.job_id)
        return _terminal(rec, _fail(req, "INVALID_RESPONSE", f"invalid transition {exc}"))
    except Exception:
        return _terminal(rec, _fail(req, "BACKEND_FAILURE", "unexpected client error"))
    if res.status is Status.CANCELLED:
        return _terminal(rec, _fail(req, "CANCELLED", res.error.message if res.error else "", Status.CANCELLED))
    return _terminal(rec, res)


def _apply(rec: JobRecord, res: JobResult) -> JobRecord:
    """Record a node-reported state. A node may finish between two observations, so queued -> completed is
    observed as queued -> running -> completed; every other skip or regression is an InvalidTransition."""
    if rec.status is Status.QUEUED and res.status is Status.COMPLETED:
        rec.advance(Status.RUNNING)
    rec.advance(res.status)
    rec.result = res
    return rec


def _terminal(rec: JobRecord, res: JobResult) -> JobResult:
    """Record a final result; an already-terminal record never changes state again."""
    if rec.status not in TERMINAL:
        rec.advance(res.status)                            # a terminal record's state is never rewritten
    rec.result = res
    return res


def _best_effort_cancel(client: NodeClient, job_id: str) -> None:
    try:
        client.cancel(job_id)
    except Exception:
        pass
