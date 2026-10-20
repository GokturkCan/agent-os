"""Deterministic routing: EVENT -> rules -> fastgate -> local -> cloud.

Pure function of (config, event, health). Every skipped stage records a
reason; every unavailable provider is recorded as a failure so it is visible
in telemetry. No stage is used on the strength of a `candidate` status.
An optional event["eligible_workers"] (from the capability plane) narrows the
worker chain; absent, routing is exactly the Run 1 behaviour.

The `fastgate` stage is a SystemOne decision step (agentos/systemone.py, R3.1): it asks one
typed question ("which pre-approved worker?") over options built from the SAME predicates the
cloud stage uses, so SystemOne can only narrow, never widen. The default backend is the null
backend, which always escalates, so routing then continues exactly as before. The human-approval
risk gate runs before any stage, hence before SystemOne. SystemOne never plans, executes, calls
tools or touches task state, and a backend error escalates instead of failing the route.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import systemone, systemone_options
from .config import USABLE, Config, activation_allowlists
from .workers import ENFORCED_WORKERS

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
    # Typed summary of the fastgate SystemOne step (None when it did not run).
    systemone: dict | None = None

    def to_dict(self):
        return asdict(self)

    def systemone_fields(self) -> dict:
        """Additive telemetry fields; empty when the SystemOne step did not run."""
        s = self.systemone
        if not s:
            return {}
        return {"systemone_backend": s["backend"], "systemone_choice": s["choice"],
                "systemone_reason": s["reason"], "systemone_escalate": s["escalate"]}


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
    # Runtime activation guard (does not rely on config.validate having run): a tier model is only
    # honoured when the protected config/systemone.yaml allowlists it. Fail closed.
    if stage == "fastgate" and model not in activation_allowlists(cfg)[1]:
        return None
    return model


def _worker_block(spec: dict, w: str, provider: str, health: dict,
                  eligible: list | None) -> tuple[bool, str | None, dict | None]:
    """Why `w` cannot serve under `provider`: (blocked, trace line, failure record).

    The single predicate behind both worker selection and the SystemOne option set, so the two
    can never disagree about what is eligible."""
    if spec.get("status") not in USABLE or spec.get("selectable") is False:
        return True, None, None
    if spec.get("launch") and w not in ENFORCED_WORKERS:
        return True, f"C4: skip worker {w}: launch adapter cannot enforce the capability profile", None
    if eligible is not None and w not in eligible:
        return True, f"C4: skip worker {w}: not capability-eligible", None
    if health.get("workers", {}).get(w) is False:
        return True, None, {"worker": w, "reason": "unhealthy at runtime"}
    if spec.get("provider") not in (None, provider):
        return True, None, None
    return False, None, None


def _pick_worker(cfg: Config, tc: dict, provider: str, health: dict, d: Decision,
                 eligible: list | None = None, only: str | None = None) -> str | None:
    workers = cfg.workers["workers"]
    for w in tc.get("workers", []):
        if only is not None and w != only:           # SystemOne narrowing (never widening)
            continue
        blocked, trace, failure = _worker_block(workers[w], w, provider, health, eligible)
        if trace:
            d.trace.append(trace)
        if failure:
            d.failures.append(failure)
        if not blocked:
            return w
    return None


def _eligible_options(cfg: Config, tc: dict, health: dict, event: dict) -> list[str]:
    """Workers the cloud stage could actually pick right now, in policy order."""
    options: list[str] = []
    for prov in tc.get("cloud_chain", []):
        if not _provider_ok(cfg, prov, health)[0]:
            continue
        for w in tc.get("workers", []):
            blocked, _, _ = _worker_block(cfg.workers["workers"][w], w, prov, health,
                                          event.get("eligible_workers"))
            if not blocked and w not in options:
                options.append(w)
    return options


def _systemone_step(cfg: Config, event: dict, health: dict, d: Decision, tc: dict, high: bool,
                    backend) -> str | None:
    """Ask SystemOne which pre-approved worker to prefer. Returns the chosen worker, or None when
    it escalated (the caller then continues the deterministic chain). Never raises."""
    info = {"backend": None, "choice": None, "reason": None, "escalate": True, "options": [],
            "confidence_kind": None}
    try:
        try:
            spec = backend if backend is not None else (cfg.routing.get("systemone") or {}).get("backend")
            # Runtime activation guard (does not rely on config.validate having run). A backend named by
            # routing.yaml (tunable, unprotected) must be built in or allowlisted in the protected
            # config/systemone.yaml. An explicit `backend` argument is code-level (benchmarks/tests), not
            # a file edit, so it is the research path and is not gated.
            if backend is None and isinstance(spec, str) and spec not in systemone.BACKENDS \
                    and spec not in activation_allowlists(cfg)[0]:
                raise ValueError(f"backend {spec!r} is not in activation.production_backends")
            be = systemone.resolve_backend(spec, cfg)
        except ValueError as exc:
            d.trace.append(f"fastgate: systemone backend unusable ({exc}); using null backend")
            be = systemone.NullBackend()
        options = _eligible_options(cfg, tc, health, event)
        info["options"] = options
        risk = "high" if high else (event.get("risk") if event.get("risk") in ("low", "medium") else "low")
        try:                                        # advisory context; failing to build it never fails routing
            opt_info = systemone_options.build(cfg, options, event.get("required_capabilities") or ())
        except Exception:
            opt_info = {}
        req = systemone.SystemOneRequest(
            task_type=d.task_type,
            questions=(systemone.Question("worker", "choose", systemone_options.QUESTION_PROMPT),),
            eligible_options=tuple(options),
            state={"task_class": d.task_class, "stage": "fastgate"},
            required_capabilities=tuple(event.get("required_capabilities") or ()),
            risk=risk,
            resource_state={k: bool(v) for k, v in (health.get("nodes") or {}).items()},
            option_info=opt_info)
        resp = systemone.system_one(req, be)
        ans = resp.answer("worker")
        info["backend"] = resp.backend
        if not resp.escalate and ans is not None and ans.choice in options:
            info.update(choice=ans.choice, reason=ans.reason_code, escalate=False,
                        confidence_kind=ans.confidence.kind)
        else:
            info["reason"] = resp.reason_code if resp.escalate else "ineligible-choice"
    except Exception as exc:                       # SystemOne must never fail the route
        info.update(backend=info["backend"] or "unknown", choice=None, reason="backend-error", escalate=True)
        d.trace.append(f"fastgate: systemone error ({type(exc).__name__}); escalating")
    d.systemone = info
    if info["escalate"]:
        d.trace.append(f"fastgate: systemone[{info['backend']}] escalated ({info['reason']}); "
                       "continuing deterministic chain")
        return None
    d.trace.append(f"fastgate: systemone[{info['backend']}] chose worker {info['choice']} "
                   f"from {info['options']} ({info['reason']})")
    return info["choice"]


def route(cfg: Config, event: dict, health: dict | None = None, *, systemone_backend=None) -> Decision:
    """Deterministic route. `systemone_backend` (a name or SystemOneBackend) overrides the
    configured one; if SystemOne's narrowing ever led to `blocked` the route is recomputed without
    it, so a SystemOne choice can never fail a task the deterministic policy could route."""
    d = _route(cfg, event, health, systemone_backend, True)
    if d.exit_state == "blocked" and d.systemone and d.systemone.get("choice"):
        info = {**d.systemone, "choice": None, "escalate": True, "reason": "unroutable-choice"}
        d2 = _route(cfg, event, health, systemone_backend, False)
        d2.systemone = info
        d2.trace = d.trace + ["fastgate: systemone choice was unroutable; re-routed deterministically "
                              "without narrowing"] + d2.trace
        return d2
    return d


def _route(cfg: Config, event: dict, health: dict | None, backend, use_systemone: bool) -> Decision:
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

    narrow: str | None = None            # worker preferred by SystemOne (always one of the eligible options)
    for stage in tc.get("stages", []):
        if stage == "fastgate" and event.get("already_classified"):
            continue
        if stage == "fastgate" and use_systemone:
            narrow = _systemone_step(cfg, event, health, d, tc, high, backend)
        if stage == "cloud":
            for prov in tc.get("cloud_chain", []):
                ok, why = _provider_ok(cfg, prov, health)
                if not ok:
                    d.trace.append(f"C4: skip {prov}: {why}")
                    if why == "unhealthy at runtime":
                        d.failures.append({"provider": prov, "reason": why})
                    d.fallbacks.append(prov)
                    continue
                worker = _pick_worker(cfg, tc, prov, health, d, event.get("eligible_workers"), only=narrow)
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
