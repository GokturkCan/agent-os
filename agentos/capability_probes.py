"""Availability / health / auth probes for registered providers (Run 2, R2.3).

Isolated from declaration: the registry never stores runtime state, and a
probe never edits the registry. Every field is tri-state so "unknown /
unprobed" is never confused with "unhealthy":

  installed  present | absent | unknown
  available  present | absent | unknown
  health     healthy | unhealthy | unknown
  auth       not_required | present | missing | unknown

Safety:
- One failing probe never breaks the capability plane: exceptions become an
  `error` on that provider's result and its fields stay unknown.
- Secrets: `env_auth` checks only whether a named variable is non-empty; the
  value is never read into a result, logged or printed. Results carry names only.
- No network: `service` probes are a placeholder that reports unknown
  (network/service probes are deferred). Health subprocesses (`--version`) run
  only with deep=True; unit tests inject state via `overrides`.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .capability_registry import _REF_SECTIONS
from .config import USABLE, expand

PRESENCE = ("present", "absent", "unknown")
HEALTH = ("healthy", "unhealthy", "unknown")
AUTH_STATES = ("not_required", "present", "missing", "unknown")
HEALTH_TIMEOUT_SECONDS = 5

# mcp.yaml `health` vocabulary -> probe fields.
_CONFIG_HEALTH = {"ok": {"health": "healthy"}, "failing": {"health": "unhealthy"},
                  "needs_auth": {"auth": "missing"}}


@dataclass(frozen=True)
class ProbeResult:
    provider: str
    installed: str = "unknown"
    available: str = "unknown"
    health: str = "unknown"
    auth: str = "unknown"
    details: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    probed: bool = False            # at least one non-declared probe actually ran

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProbeContext:
    """Injectable environment so probes are deterministic under test."""
    cfg: object | None = None
    deep: bool = False
    env: dict = field(default_factory=lambda: dict(os.environ))
    which: object = shutil.which
    plugins_file: Path | None = None
    run: object = None              # subprocess runner for deep health checks


def _merge(values: list[str], negative: str) -> str:
    """Negative evidence wins; otherwise the first known value; else unknown."""
    if negative in values:
        return negative
    return next((v for v in values if v != "unknown"), "unknown")


# ------------------------------------------------------------------ probes
def _probe_executable(spec: dict, ctx: ProbeContext) -> dict:
    target = str(spec["target"])
    path = ctx.which(expand(target).name) if "/" not in target else (
        str(expand(target)) if expand(target).exists() else None)
    if not path:
        return {"installed": "absent", "available": "absent", "detail": f"{target}: not found"}
    out = {"installed": "present", "available": "present", "detail": f"{target}: found"}
    if ctx.deep and spec.get("health_args"):
        run = ctx.run or (lambda argv: subprocess.run(argv, capture_output=True, text=True,
                                                      timeout=HEALTH_TIMEOUT_SECONDS))
        try:
            r = run([path, *map(str, spec["health_args"])])
            ok = r.returncode == 0
            out["health"] = "healthy" if ok else "unhealthy"
            out["detail"] += f"; health check exit {r.returncode}"   # exit code only, never output
        except (subprocess.TimeoutExpired, OSError) as exc:
            out["health"] = "unhealthy"
            out["detail"] += f"; health check failed: {type(exc).__name__}"
    return out


def _probe_claude_plugin(spec: dict, ctx: ProbeContext) -> dict:
    f = ctx.plugins_file or Path(ctx.env.get("AGENTOS_CLAUDE_PLUGINS_FILE",
                                             Path.home() / ".claude" / "plugins" / "installed_plugins.json"))
    if not Path(f).exists():
        return {"detail": "claude plugin index not found"}
    data = json.loads(Path(f).read_text())
    names = data.get("plugins", data) if isinstance(data, dict) else {}
    hit = any(str(k).split("@", 1)[0] == spec["target"] for k in names)
    state = "present" if hit else "absent"
    return {"installed": state, "available": state,
            "detail": f"claude plugin {spec['target']}: {'installed' if hit else 'not installed'}"}


def _probe_path(spec: dict, ctx: ProbeContext) -> dict:
    for pattern in spec["paths"]:
        if glob.glob(str(expand(pattern))):
            return {"installed": "present", "available": "present", "detail": "path found"}
    return {"installed": "absent", "available": "absent", "detail": "no matching path"}


def _probe_env_auth(spec: dict, ctx: ProbeContext) -> dict:
    names = list(spec["env"])
    present = [n for n in names if ctx.env.get(n)]           # truthiness only; value never kept
    return {"auth": "present" if present else "missing",
            "detail": f"auth env {'set' if present else 'unset'}: {', '.join(present or names)}"}


def _probe_config_health(spec: dict, ctx: ProbeContext) -> dict:
    if ctx.cfg is None:
        return {"detail": "config health: no config supplied"}
    section, _, name = spec["ref"].partition(".")
    file_key, sub = _REF_SECTIONS.get(section, (section, section))
    entry = (ctx.cfg.data.get(file_key) or {}).get(sub, {}).get(name)
    if entry is None:
        return {"detail": f"config health: {spec['ref']} not found"}
    out = dict(_CONFIG_HEALTH.get(entry.get("health"), {}))
    if entry.get("status") in USABLE:
        out.setdefault("installed", "present")
    out["detail"] = f"last observed {spec['ref']}: status={entry.get('status')} health={entry.get('health')}"
    return out


def _probe_service(spec: dict, ctx: ProbeContext) -> dict:
    return {"detail": "service probe deferred (no network probes in Run 2)"}


def _probe_declared(spec: dict, ctx: ProbeContext) -> dict:
    return {"detail": "declared only; no probe defined"}


PROBES = {"executable": _probe_executable, "claude_plugin": _probe_claude_plugin, "path": _probe_path,
          "env_auth": _probe_env_auth, "config_health": _probe_config_health, "service": _probe_service,
          "declared": _probe_declared}
_INERT = ("service", "declared")


def probe_provider(provider, ctx: ProbeContext | None = None) -> ProbeResult:
    ctx = ctx or ProbeContext()
    parts, details, errors, probed = [], [], [], False
    for spec in provider.probe:
        kind = spec.get("type")
        try:
            out = PROBES[kind](spec, ctx)
        except Exception as exc:          # isolate: one bad probe never breaks the plane
            errors.append(f"{kind}: {type(exc).__name__}")
            continue
        probed = probed or kind not in _INERT
        details.append(out.pop("detail", kind))
        parts.append(out)

    def field_(name, negative):
        return _merge([p[name] for p in parts if name in p], negative)

    auth = "not_required" if provider.auth == "none" else field_("auth", "missing")
    return ProbeResult(provider=provider.id, installed=field_("installed", "absent"),
                       available=field_("available", "absent"),
                       health=field_("health", "unhealthy"), auth=auth,
                       details=tuple(details), errors=tuple(errors), probed=probed)


def apply_override(result: ProbeResult, override: dict) -> ProbeResult:
    allowed = {"installed": PRESENCE, "available": PRESENCE, "health": HEALTH, "auth": AUTH_STATES}
    for k, v in override.items():
        if k not in allowed or v not in allowed[k]:
            raise ValueError(f"invalid probe override {k}={v!r}")
    return replace(result, **override, details=result.details + ("override",))


def probe_all(registry, ctx: ProbeContext | None = None, overrides: dict | None = None) -> dict[str, ProbeResult]:
    """Probe every registered provider. `overrides` ({id: {field: state}}) lets
    callers/tests inject deterministic states without touching the machine."""
    ctx = ctx or ProbeContext()
    overrides = overrides or {}
    out = {}
    for pid, p in sorted(registry.providers.items()):
        r = probe_provider(p, ctx)
        if pid in overrides:
            r = apply_override(r, overrides[pid])
        out[pid] = r
    return out


def static_probes(registry, states: dict | None = None, default: dict | None = None) -> dict[str, ProbeResult]:
    """Fully synthetic probe results (no machine access). `default` applies to
    every provider, `states` per provider; auth=none providers stay not_required."""
    default = default or {}
    out = {}
    for pid, p in sorted(registry.providers.items()):
        base = ProbeResult(provider=pid, auth="not_required" if p.auth == "none" else "unknown")
        merged = {**default, **(states or {}).get(pid, {})}
        if p.auth == "none":
            merged.pop("auth", None)
        out[pid] = apply_override(base, merged) if merged else base
    return out
