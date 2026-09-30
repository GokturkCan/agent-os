"""Deterministic routing: EVENT -> rules -> fastgate -> local -> cloud.

Pure function of (config, event, health). Every skipped stage records a
reason; every unavailable provider is recorded as a failure so it is visible
in telemetry. No stage is used on the strength of a `candidate` status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import USABLE, Config

LOCAL_STAGE_PROVIDER = {"local_primary": "local_msi", "local_fallback": "local_mac"}


@dataclass
class Decision:
    task_type: str
    task_class: str | None = None
    handler: str | None = None          # "deterministic" | "model"
    stage: str | None = None
    provider: str | None = None
    model: str | None = None
    worker: str | None = None
    requires_human_approval: bool = False
    exit_state: str | None = None       # set when the task cannot be routed
    trace: list = field(default_factory=list)
    fallbacks: list = field(default_factory=list)
    failures: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _provider_ok(cfg: Config, name: str, health: dict) -> tuple[bool, str]:
    p = cfg.providers["providers"].get(name)
    if p is None:
        return False, "unknown provider"
    if not p.get("enabled"):
        return False, f"disabled (status={p.get('status')})"
    if p.get("status") not in USABLE:
        return False, f"status={p.get('status')}"
    if health.get("providers", {}).get(name) is False:
        return False, "unhealthy at runtime"
    return True, "ok"


def _tier_model(cfg: Config, stage: str) -> str | None:
    model = cfg.models["tiers"].get(stage, {}).get("model")
    if not model:
        return None
    if cfg.models["models"].get(model, {}).get("status") not in USABLE:
        return None
    return model


def _pick_worker(cfg: Config, tc: dict, provider: str, health: dict, d: Decision) -> str | None:
    workers = cfg.workers["workers"]
    for w in tc.get("workers", []):
        spec = workers[w]
        if spec.get("status") not in USABLE or spec.get("selectable") is False:
            continue
        if health.get("workers", {}).get(w) is False:
            d.failures.append({"worker": w, "reason": "unhealthy at runtime"})
            continue
        if spec.get("provider") in (None, provider):
            return w
    return None


def route(cfg: Config, event: dict, health: dict | None = None) -> Decision:
    health = health or {}
    r = cfg.routing
    ttype = event["type"]
    d = Decision(task_type=ttype)

    markers = set(event.get("markers", []))
    high = event.get("risk") == "high" or bool(markers & set(r["risk"]["high_risk_task_markers"]))
    if high and r["risk"].get("high_requires_human_approval"):
        d.requires_human_approval = True
        d.trace.append("risk: high -> human approval required regardless of classifier confidence")
        if not event.get("human_approval_ref"):
            d.exit_state = "human_handoff"
            return d

    if ttype in r.get("deterministic_rules", {}):
        d.handler, d.stage = "deterministic", "C0"
        d.trace.append(f"C0: deterministic rule for {ttype}; no model invoked")
        return d

    d.task_class = event.get("task_class") or ttype
    tc = r["task_classes"].get(d.task_class)
    if tc is None:
        d.exit_state = "blocked"
        d.trace.append(f"no task class '{d.task_class}' in routing policy")
        return d
    d.handler = "model"

    if tc.get("requires_resource"):
        node = tc["requires_resource"]
        if not health.get("nodes", {}).get(node, False):
            d.exit_state = "blocked"
            d.failures.append({"node": node, "reason": "unreachable"})
            d.trace.append(f"{node} unreachable -> blocked; Mac control plane unaffected")
        else:
            d.stage = "resource"
            d.trace.append(f"route to resource scheduler on {node}")
        return d

    for stage in tc.get("stages", []):
        if stage == "fastgate" and event.get("already_classified"):
            continue
        if stage == "cloud":
            for prov in tc.get("cloud_chain", []):
                ok, why = _provider_ok(cfg, prov, health)
                if not ok:
                    d.trace.append(f"C4: skip {prov}: {why}")
                    if why == "unhealthy at runtime":
                        d.failures.append({"provider": prov, "reason": why})
                    d.fallbacks.append(prov)
                    continue
                worker = _pick_worker(cfg, tc, prov, health, d)
                if tc.get("workers") and worker is None:
                    d.trace.append(f"C4: {prov} ok but no usable worker for it")
                    d.fallbacks.append(prov)
                    continue
                d.stage, d.provider, d.worker = "cloud", prov, worker
                d.trace.append(f"C4: selected {prov} via {worker}")
                if d.fallbacks:
                    d.trace.append(f"fallback used after: {d.fallbacks}")
                return d
            continue
        model = _tier_model(cfg, stage)
        if model is None:
            d.trace.append(f"{stage}: skip — no usable model (candidates only)")
            continue
        prov = LOCAL_STAGE_PROVIDER.get(stage)
        host = cfg.models["models"][model].get("host")
        if host and not health.get("nodes", {}).get(host, host == "mac"):
            d.trace.append(f"{stage}: skip — host {host} unreachable")
            d.failures.append({"node": host, "reason": "unreachable"})
            continue
        if prov:
            ok, why = _provider_ok(cfg, prov, health)
            if not ok:
                d.trace.append(f"{stage}: skip {prov}: {why}")
                continue
        if stage == "fastgate":
            d.trace.append(f"fastgate: classified by {model}")
            continue  # classification only; continue to reasoning stages
        d.stage, d.provider, d.model = stage, prov, model
        d.trace.append(f"{stage}: selected {model}")
        return d

    d.exit_state = "blocked"
    d.trace.append("all stages/providers unavailable -> blocked")
    return d


def route_tool(cfg: Config, need: str, health: dict | None = None) -> dict:
    """Select the narrowest usable tool for an information/interaction need."""
    health = health or {}
    rule = cfg.routing["tool_routing"].get(need)
    if rule is None:
        return {"tool": None, "trace": [f"no tool routing for need '{need}'"]}
    tools = cfg.mcp["tools"]
    trace = []
    for t in [rule["prefer"], *rule.get("fallback", [])]:
        spec = tools[t]
        h = health.get("tools", {}).get(t, spec.get("health", "ok"))
        if spec.get("status") not in USABLE:
            trace.append(f"skip {t}: status={spec.get('status')}")
            continue
        if h in ("failing", "needs_auth", False):
            trace.append(f"skip {t}: health={h}")
            continue
        trace.append(f"selected {t}")
        return {"tool": t, "trace": trace}
    return {"tool": None, "trace": trace + ["no usable tool"]}
