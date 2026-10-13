"""Deterministic capability eligibility, selection and fallback (Run 2, R2.4/R2.5/R2.7).

Pure function of (registry, request, probe results) — no LLM, no network, no
randomness. Flow:

  required capabilities (explicit | task contract | task_type mapping)
    -> per provider: hard filters (adoption, deny, cost/locality/risk caps,
       host, availability, health, auth)            -> rejection reason codes
    -> per capability: eligible providers, ranked
    -> per executor: can it cover every capability natively or through an
       eligible tool it integrates with?              -> eligible executors
    -> rank (policy key) -> selected executor + tools + ordered fallbacks
    -> no eligible executor => status=blocked (handoff), never a guess

Ranking key (earlier component decides; hard filters already applied, so
quality/risk constraints always override cost preference):
  capability preference -> verified state -> cost -> locality -> latency
  -> provider preference -> id

This module narrows and explains; it does not orchestrate. Hermes stays the
sole orchestrator and agentos/router.py stays the routing authority — dispatch
passes the eligible worker set to the router as a constraint.
A future SystemOne/FastGate (agentos/systemone.py) may only choose among the
`eligible_executors` this produces.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .capability_registry import (COST, LATENCY, LOCALITY, REJECTION_REASONS, RISK,
                                  SELECTION_REASONS, HOSTS, Provider, Registry)

# Rank-key component -> the reason code reported when that component decided.
KEY_REASONS = ("capability-preferred", "verified-state-preferred", "cost-preferred", "local-preferred",
               "latency-preferred", "preference-order", "id-tiebreak")
assert set(KEY_REASONS) <= set(SELECTION_REASONS)


@dataclass(frozen=True)
class CapabilityRequest:
    required: tuple[str, ...] = ()
    task_id: str | None = None
    task_type: str | None = None
    hosts: tuple[str, ...] = ()          # allowed hosts (empty == any)
    max_cost: str | None = None          # hard cap, e.g. "existing_subscription"
    localities: tuple[str, ...] = ()     # allowed localities (empty == any)
    max_risk: str | None = None
    deny: tuple[str, ...] = ()           # provider ids excluded by hard policy
    strict: bool = False                 # reject unknown health/auth instead of ranking them last

    def __post_init__(self):
        for name, value, allowed in (("max_cost", self.max_cost, COST), ("max_risk", self.max_risk, RISK)):
            if value is not None and value not in allowed:
                raise ValueError(f"invalid {name} {value!r}")
        for h in self.hosts:
            if h not in HOSTS:
                raise ValueError(f"invalid host {h!r}")
        for loc in self.localities:
            if loc not in LOCALITY:
                raise ValueError(f"invalid locality {loc!r}")


@dataclass
class Rejection:
    reasons: list[str]
    details: list[str]


@dataclass
class CapabilityResolution:
    capability: str
    known: bool
    eligible: list[str] = field(default_factory=list)       # ranked, best first
    rejected: dict[str, Rejection] = field(default_factory=dict)
    selected: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class CapabilityPlan:
    required: list[str]
    status: str                                             # selected | blocked
    task_id: str | None = None
    exit_state: str | None = None                           # None | blocked
    executor: str | None = None
    worker: str | None = None                               # workers.yaml name of the executor
    reasons: list[str] = field(default_factory=list)
    tools: dict[str, str] = field(default_factory=dict)     # capability -> provider (executor id == native)
    tool_fallbacks: dict[str, list[str]] = field(default_factory=dict)
    tools_by_executor: dict[str, dict[str, str]] = field(default_factory=dict)  # per eligible executor
    eligible_executors: list[str] = field(default_factory=list)   # ranked; [0] == executor
    eligible_workers: list[str] = field(default_factory=list)
    rejected_executors: dict[str, Rejection] = field(default_factory=dict)
    unknown_capabilities: list[str] = field(default_factory=list)
    by_capability: dict[str, CapabilityResolution] = field(default_factory=dict)
    flags: dict[str, list[str]] = field(default_factory=dict)     # eligible-with-caveat markers
    metadata: dict[str, dict] = field(default_factory=dict)       # cost/locality of chosen providers
    handoff: list[str] = field(default_factory=list)
    next_step: str | None = None

    @property
    def fallbacks(self) -> list[str]:
        return self.eligible_executors[1:]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fallbacks"] = self.fallbacks
        return d

    def explain(self) -> list[str]:
        lines = [f"required: {', '.join(self.required) or '(none)'}", f"status: {self.status}"]
        if self.unknown_capabilities:
            lines.append(f"unknown capabilities: {', '.join(self.unknown_capabilities)} (unknown-capability)")
        if self.executor:
            lines.append(f"selected executor: {self.executor} [{', '.join(self.reasons)}]")
            for cap, pid in self.tools.items():
                via = "native" if pid == self.executor else pid
                fb = self.tool_fallbacks.get(cap) or []
                lines.append(f"  {cap} -> {via}" + (f" (fallbacks: {', '.join(fb)})" if fb else ""))
            lines.append(f"executor fallbacks: {', '.join(self.fallbacks) or '-'}")
        for pid, rej in self.rejected_executors.items():
            lines.append(f"rejected executor {pid}: {', '.join(rej.reasons)} — {'; '.join(rej.details)}")
        for cap, res in self.by_capability.items():
            elig = ", ".join(res.eligible) or "-"
            lines.append(f"capability {cap}: eligible [{elig}]")
            for pid, rej in res.rejected.items():
                lines.append(f"  rejected {pid}: {', '.join(rej.reasons)} — {'; '.join(rej.details)}")
        if self.handoff:
            lines.append("handoff: " + "; ".join(self.handoff))
        if self.next_step:
            lines.append(f"next: {self.next_step}")
        return lines


# ------------------------------------------------------------ requirements
def resolve_required(registry: Registry, explicit=(), task_type: str | None = None,
                     contract: dict | None = None) -> tuple[str, ...]:
    """Deterministic union of explicit capabilities, a task contract's
    `required_capabilities`, and the policy's task_type mapping. No inference
    from natural language."""
    caps = set(explicit or ())
    caps |= set((contract or {}).get("required_capabilities") or ())
    caps |= set(registry.policy.capabilities_for_task_type(task_type))
    return tuple(sorted(caps))


# ------------------------------------------------------------ eligibility
def evaluate_provider(p: Provider, probe, request: CapabilityRequest, policy) -> tuple[Rejection, list[str]]:
    """Hard filters for one provider. Returns (rejection, caveat_flags); an empty
    rejection.reasons means the provider passed every filter."""
    reasons, details, flags = [], [], []

    def reject(code, detail):
        if code not in reasons:
            reasons.append(code)
        details.append(detail)

    if p.id in request.deny:
        reject("policy-blocked", "denied by request policy")
    if p.adoption not in policy.runtime_adoption:
        reject("policy-blocked", f"adoption={p.adoption} is not runtime-eligible")
    if request.max_cost and COST.index(p.cost) > COST.index(request.max_cost):
        reject("policy-blocked", f"cost {p.cost} exceeds cap {request.max_cost}")
    if request.localities and p.locality not in request.localities:
        reject("policy-blocked", f"locality {p.locality} not allowed")
    if request.max_risk and RISK.index(p.risk) > RISK.index(request.max_risk):
        reject("policy-blocked", f"risk {p.risk} exceeds cap {request.max_risk}")
    if request.hosts and "any" not in p.hosts and not set(p.hosts) & set(request.hosts):
        reject("host-mismatch", f"hosts {list(p.hosts)} not in {list(request.hosts)}")

    if probe.available == "absent":
        reject("provider-unavailable", "not installed/available")
    elif probe.available == "unknown":
        if request.strict or not policy.allow_unknown_availability:
            reject("availability-unknown", "availability not established by any probe")
        else:
            flags.append("availability-unverified")
    if probe.health == "unhealthy":
        reject("provider-unhealthy", "health check failed")
    elif probe.health == "unknown":
        if request.strict or not policy.allow_unknown_health:
            reject("health-unknown", "health not verified")
        else:
            flags.append("health-unverified")
    if p.auth == "required":
        if probe.auth == "missing":
            reject("auth-missing", "authentication required but missing")
        elif probe.auth == "unknown":
            if request.strict or not policy.allow_unknown_auth:
                reject("auth-unknown", "authentication state not verified")
            else:
                flags.append("auth-unverified")
    elif p.auth == "optional" and probe.auth == "missing":
        flags.append("auth-optional-absent")
    assert set(reasons) <= set(REJECTION_REASONS)
    return Rejection(reasons, details), flags


def _verified(p: Provider, probe) -> int:
    auth_ok = p.auth != "required" or probe.auth == "present"
    return 0 if probe.health == "healthy" and probe.available == "present" and auth_ok else 1


def _pref_index(policy, cap: str, pid: str) -> int:
    prefs = policy.preferences_for(cap)
    return prefs.index(pid) if pid in prefs else len(prefs)


def rank_key(p: Provider, probe, policy, pref: int = 0) -> tuple:
    return (pref, _verified(p, probe), COST.index(p.cost), LOCALITY.index(p.locality),
            LATENCY.index(p.latency), p.preference, p.id)


def _why(keys: list[tuple]) -> list[str]:
    """Reason the first key beat the runner-up (first differing component)."""
    if len(keys) < 2:
        return ["only-eligible-candidate"]
    for i, (a, b) in enumerate(zip(keys[0], keys[1])):
        if a != b:
            return [KEY_REASONS[i]]
    return ["id-tiebreak"]


def integration_state(executor: Provider, tool: Provider) -> str:
    """supported | unsupported | unknown. Explicit executor declarations win;
    otherwise a tool whose `requires` are all native to the executor (e.g. a CLI
    needing devops.shell) is supported; anything else stays unknown."""
    explicit = executor.integration(tool.id)
    if explicit:
        return explicit
    if tool.requires and set(tool.requires) <= set(executor.capabilities):
        return "supported"
    return "unknown"


# ------------------------------------------------------------ planning
def plan(registry: Registry, request: CapabilityRequest, probes: dict) -> CapabilityPlan:
    policy = registry.policy
    required = sorted(set(request.required))
    out = CapabilityPlan(required=required, status="blocked", task_id=request.task_id)
    out.unknown_capabilities = [c for c in required if not registry.is_known_capability(c)]
    known = [c for c in required if registry.is_known_capability(c)]

    passed: dict[str, bool] = {}
    for pid, p in sorted(registry.providers.items()):
        rej, flags = evaluate_provider(p, probes[pid], request, policy)
        passed[pid] = not rej.reasons
        if flags:
            out.flags[pid] = flags
        for cap in p.capabilities:
            if cap in known:
                res = out.by_capability.setdefault(cap, CapabilityResolution(cap, True))
                if rej.reasons:
                    res.rejected[pid] = rej
    for cap in known:
        res = out.by_capability.setdefault(cap, CapabilityResolution(cap, True))
        cands = [p for p in registry.providers_for(cap) if passed[p.id]]
        keys = sorted(rank_key(p, probes[p.id], policy, _pref_index(policy, cap, p.id)) for p in cands)
        res.eligible = [k[-1] for k in keys]
        if res.eligible:
            res.selected = res.eligible[0]
            res.reasons = _why(keys) + ([policy.reason_for(cap)] if policy.reason_for(cap) else [])
    for cap in out.unknown_capabilities:
        out.by_capability[cap] = CapabilityResolution(cap, False)

    # Executors: cover every known capability natively or via an integrated eligible tool.
    exec_keys, means_by_exec = [], {}
    for e in sorted(registry.executors(), key=lambda p: p.id):
        rej, _ = evaluate_provider(e, probes[e.id], request, policy)
        if rej.reasons:
            out.rejected_executors[e.id] = rej
            continue
        means, missing = {}, Rejection([], [])
        for cap in known:
            res = out.by_capability[cap]
            options, blocked = [], []
            for tid in res.eligible:
                t = registry.get(tid)
                if t.is_executor:
                    continue
                state = integration_state(e, t)
                if state == "supported":
                    options.append(tid)
                else:
                    blocked.append((tid, f"integration-{state}"))
            if cap in e.capabilities:
                options.append(e.id)
            # Policy-preferred tools first, then native, then remaining tools by rank.
            options.sort(key=lambda pid: (_pref_index(policy, cap, pid), pid != e.id, res.eligible.index(pid)
                                          if pid in res.eligible else len(res.eligible)))
            if options:
                means[cap] = options
                continue
            if "capability-missing" not in missing.reasons:
                missing.reasons.append("capability-missing")
            for tid, code in blocked:
                if code not in missing.reasons:
                    missing.reasons.append(code)
            why = ", ".join(f"{tid} {code}" for tid, code in blocked) or (
                "no eligible provider (" + ", ".join(f"{pid}: {'/'.join(r.reasons)}"
                                                     for pid, r in res.rejected.items()) + ")"
                if res.rejected else "no provider declares it")
            missing.details.append(f"{cap}: {why}")
        if out.unknown_capabilities:
            missing.reasons.append("unknown-capability")
            missing.details.append(f"unknown: {', '.join(out.unknown_capabilities)}")
        if missing.reasons:
            out.rejected_executors[e.id] = missing
            continue
        pref = sum(_pref_index(policy, cap, opts[0]) for cap, opts in means.items())
        exec_keys.append(rank_key(e, probes[e.id], policy, pref))
        means_by_exec[e.id] = means

    exec_keys.sort()
    out.eligible_executors = [k[-1] for k in exec_keys]
    out.tools_by_executor = {e: {cap: opts[0] for cap, opts in m.items()} for e, m in means_by_exec.items()}
    out.eligible_workers = [registry.get(e).worker_name for e in out.eligible_executors]
    if not out.eligible_executors:
        out.exit_state = "blocked"
        out.reasons = ["unknown-capability"] if out.unknown_capabilities else ["no-eligible-provider"]
        out.handoff = _handoff_items(out)
        out.next_step = ("human handoff: no registered executor can satisfy the required capabilities; "
                         "install/enable/authenticate a listed provider or change the request")
        return out

    out.status = "selected"
    out.executor = out.eligible_executors[0]
    ex = registry.get(out.executor)
    out.worker = ex.worker_name
    out.reasons = _why(exec_keys)
    for cap in known:
        code = policy.reason_for(cap)
        if code and code not in out.reasons:
            out.reasons.append(code)
    means = means_by_exec[out.executor]
    out.tools = {cap: opts[0] for cap, opts in means.items()}
    out.tool_fallbacks = {cap: opts[1:] for cap, opts in means.items() if opts[1:]}
    for pid in sorted({out.executor, *out.tools.values()}):
        p = registry.get(pid)
        out.metadata[pid] = {"kind": p.kind, "cost": p.cost, "locality": p.locality, "latency": p.latency}
    return out


def _handoff_items(out: CapabilityPlan) -> list[str]:
    items = [f"{c}: unknown-capability" for c in out.unknown_capabilities]
    for cap, res in out.by_capability.items():
        if res.known and not res.eligible:
            rej = ", ".join(f"{pid} ({'/'.join(r.reasons)})" for pid, r in res.rejected.items())
            items.append(f"{cap}: {rej or 'no provider registered'}")
    if not items:  # providers exist per capability, but no executor can reach them
        items = [f"{pid}: {', '.join(r.reasons)}" for pid, r in out.rejected_executors.items()]
    return items


# ------------------------------------------------------------ parity (R2.8)
def parity_matrix(registry: Registry, probes: dict | None = None) -> dict:
    """Executor x (capability | provider) matrix. Not a parity claim: it states
    what each executor can reach, and leaves undeclared things `unknown`.

    Capability column: native | via (adopted providers it integrates with) | unknown.
    Provider column:   supported | unsupported | unknown, with the source
    (explicit declaration, derived from `requires`, or default unknown) and,
    when probes are given, that provider's availability."""
    cols = list(registry.policy.parity_columns)
    rows = {}
    for e in sorted(registry.executors(), key=lambda p: p.id):
        row = {}
        for col in cols:
            if col in registry.capabilities:
                if col in e.capabilities:
                    row[col] = {"state": "native", "via": []}
                    continue
                via = [p.id for p in registry.providers_for(col) if not p.is_executor
                       and p.adoption in registry.policy.runtime_adoption
                       and integration_state(e, p) == "supported"]
                row[col] = {"state": "via" if via else "unknown", "via": via}
            else:
                t = registry.get(col)
                state = integration_state(e, t)
                source = ("explicit" if e.integration(col) else
                          "derived" if state == "supported" else "default")
                cell = {"state": state, "source": source}
                if probes is not None:
                    cell["available"] = probes[col].available
                    cell["health"] = probes[col].health
                row[col] = cell
        if probes is not None:
            row["_executor"] = {"available": probes[e.id].available, "health": probes[e.id].health,
                                "auth": probes[e.id].auth}
        rows[e.id] = row
    return {"columns": cols, "rows": rows}


# ------------------------------------------------------------ telemetry
def telemetry_payload(plan: CapabilityPlan) -> dict:
    """Compact, secret-free decision summary: registry ids, enum values and
    reason codes only (no probe details, paths or free text)."""
    meta = plan.metadata.get(plan.executor or "", {})
    return {
        "required": list(plan.required), "status": plan.status, "exit_state": plan.exit_state,
        "executor": plan.executor, "worker": plan.worker, "reasons": list(plan.reasons),
        "tools": dict(plan.tools), "tool_fallbacks": {k: list(v) for k, v in plan.tool_fallbacks.items()},
        "eligible": list(plan.eligible_executors), "fallbacks": plan.fallbacks,
        "rejected": {pid: list(r.reasons) for pid, r in plan.rejected_executors.items()},
        "rejected_tools": {cap: {pid: list(r.reasons) for pid, r in res.rejected.items()}
                           for cap, res in plan.by_capability.items() if res.rejected},
        "unknown_capabilities": list(plan.unknown_capabilities),
        "cost": meta.get("cost"), "locality": meta.get("locality"),
    }


def emit_decision(plan: CapabilityPlan, task_id: str | None = None) -> dict | None:
    """Record a `capability_decision` event. Never raises: telemetry failure
    must not change or break the selection."""
    from . import events
    try:
        payload = telemetry_payload(plan)
    except Exception as exc:
        payload = {"error": type(exc).__name__}
    return events.emit("capability_decision", task_id=task_id or plan.task_id, worker=plan.worker,
                       status=plan.status, exit_state=plan.exit_state, detail=",".join(plan.reasons),
                       capabilities=payload)


# ------------------------------------------------------------ convenience
def selected_mcp(cfg, registry: Registry, plan: CapabilityPlan, worker: str | None) -> tuple[str, ...]:
    """config/mcp.yaml names of the MCP servers the plan selected for `worker`.

    Only providers of kind `mcp` whose config_ref points at an mcp.yaml entry
    with a launch definition qualify; native executor capabilities and
    CLI/skill/service providers never become MCP servers. Whether the worker's
    profile may actually receive a server is still decided at launch
    (workers.mcp_servers_for checks the profile grant)."""
    executor = next((e for e, w in zip(plan.eligible_executors, plan.eligible_workers) if w == worker), None)
    names = []
    for pid in sorted(set(plan.tools_by_executor.get(executor, {}).values())):
        p = registry.providers.get(pid)
        if p is None or p.kind != "mcp" or not (p.config_ref or "").startswith("mcp."):
            continue
        name = p.config_ref.split(".", 1)[1]
        spec = cfg.mcp["tools"].get(name) or {}
        if spec.get("kind") == "mcp" and "launch" in spec:
            names.append(name)
    return tuple(names)


def plan_for(cfg, required=(), *, task_id: str | None = None, task_type: str | None = None,
             contract: dict | None = None, overrides: dict | None = None, probes: dict | None = None,
             deep: bool = False, registry: Registry | None = None, **constraints) -> CapabilityPlan:
    """Load the registry (unless given), run local probes (no network) and plan."""
    from . import capability_probes, capability_registry
    reg = registry or capability_registry.load(cfg)
    caps = resolve_required(reg, required, task_type, contract)
    if probes is None:
        probes = capability_probes.probe_all(reg, capability_probes.ProbeContext(cfg=cfg, deep=deep), overrides)
    return plan(reg, CapabilityRequest(required=caps, task_id=task_id, task_type=task_type, **constraints),
                probes)
