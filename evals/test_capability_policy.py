"""Run 2 / R2.4, R2.5 — required capabilities, eligibility filters, deterministic ranking,
fallback ordering and explanation reason codes (synthetic registries + static probes)."""
import pytest

from agentos import capability_policy as CP
from agentos import capability_probes as P
from agentos import capability_registry as R

CATALOG = {c: c for c in ("code.edit", "code.references", "web.interact", "web.docs_lookup",
                          "devops.shell", "devops.github", "code.snapshot")}
OK = {"available": "present", "health": "healthy", "auth": "present"}


def _reg(providers, policy=None):
    data = {"version": 1, "capabilities": CATALOG, "providers": providers, "policy": policy or {}}
    reg, errs = R.parse(data)
    assert errs == [], errs
    return reg


def _w(pid, caps=("code.edit", "devops.shell"), **kw):
    return {"id": pid, "kind": "worker", "adoption": "adopted", "capabilities": list(caps),
            "locality": "cloud", "cost": "existing_subscription", "latency": "network", "hosts": ["mac"],
            "auth": "required", **kw}


def _t(pid, caps, **kw):
    base = {"id": pid, "kind": "mcp", "adoption": "adopted", "capabilities": list(caps), "locality": "local",
            "cost": "free", "latency": "local_fast", "hosts": ["any"], "auth": "none"}
    base.update(kw)
    return base


def _plan(reg, required, states=None, default=OK, **req):
    probes = P.static_probes(reg, states=states, default=default)
    return CP.plan(reg, CP.CapabilityRequest(required=tuple(required), **req), probes)


# ------------------------------------------------------------ requirements
def test_resolve_required_is_deterministic_union(cfg):
    reg = R.load(cfg)
    caps = CP.resolve_required(reg, ["web.interact", "code.edit"], task_type="coding",
                               contract={"required_capabilities": ["devops.git"]})
    assert caps == ("code.edit", "code.test", "devops.git", "web.interact")
    assert CP.resolve_required(reg, task_type="github") == ("devops.github",)
    assert CP.resolve_required(reg, task_type="not-mapped") == ()
    assert CP.resolve_required(reg) == ()


def test_request_constraints_are_validated():
    with pytest.raises(ValueError):
        CP.CapabilityRequest(max_cost="cheap")
    with pytest.raises(ValueError):
        CP.CapabilityRequest(hosts=("pluto",))
    with pytest.raises(ValueError):
        CP.CapabilityRequest(localities=("moon",))


# ------------------------------------------------------------ eligibility
def test_multi_capability_matching_combines_native_and_tools():
    reg = _reg([_w("alpha", integrations={"refs": "supported"}), _t("refs", ["code.references"])])
    pl = _plan(reg, ["code.edit", "code.references"])
    assert pl.status == "selected" and pl.executor == "alpha"
    assert pl.tools == {"code.edit": "alpha", "code.references": "refs"}


def test_executor_without_integration_cannot_claim_tool_capability():
    reg = _reg([_w("alpha", integrations={"refs": "unsupported"}), _w("beta"), _t("refs", ["code.references"])])
    pl = _plan(reg, ["code.references"])
    assert pl.status == "blocked"
    assert pl.rejected_executors["alpha"].reasons == ["capability-missing", "integration-unsupported"]
    assert pl.rejected_executors["beta"].reasons == ["capability-missing", "integration-unknown"]


def test_derived_integration_via_requires():
    reg = _reg([_w("alpha"), _t("packer", ["code.snapshot"], kind="cli", requires=["devops.shell"])])
    assert _plan(reg, ["code.snapshot"]).tools == {"code.snapshot": "packer"}
    assert CP.integration_state(reg.get("alpha"), reg.get("packer")) == "supported"


@pytest.mark.parametrize("state,code", [
    ({"available": "absent"}, "provider-unavailable"),
    ({"available": "unknown"}, "availability-unknown"),
    ({"health": "unhealthy"}, "provider-unhealthy"),
])
def test_unavailable_unhealthy_unknown_availability_filtered(state, code):
    reg = _reg([_w("alpha", integrations={"refs": "supported"}), _t("refs", ["code.references"])])
    pl = _plan(reg, ["code.references"], states={"refs": state})
    assert pl.status == "blocked" and pl.exit_state == "blocked"
    assert code in pl.by_capability["code.references"].rejected["refs"].reasons


def test_auth_required_filtering_and_optional_auth():
    reg = _reg([_w("alpha", integrations={"docs": "supported"}),
                _t("docs", ["web.docs_lookup"], auth="required")])
    pl = _plan(reg, ["web.docs_lookup"], states={"docs": {"auth": "missing"}})
    assert pl.by_capability["web.docs_lookup"].rejected["docs"].reasons == ["auth-missing"]
    reg2 = _reg([_w("alpha", integrations={"docs": "supported"}),
                 _t("docs", ["web.docs_lookup"], auth="optional")])
    pl2 = _plan(reg2, ["web.docs_lookup"], states={"docs": {"auth": "missing"}})
    assert pl2.status == "selected" and "auth-optional-absent" in pl2.flags["docs"]


def test_unknown_health_and_auth_allowed_but_flagged_and_ranked_last():
    reg = _reg([_w("alpha"), _w("beta")])
    pl = _plan(reg, ["code.edit"], states={"alpha": {"health": "unknown", "auth": "unknown"}})
    assert pl.eligible_executors == ["beta", "alpha"]               # verified beats unknown
    assert pl.reasons[0] == "verified-state-preferred"
    assert {"health-unverified", "auth-unverified"} <= set(pl.flags["alpha"])


def test_strict_request_rejects_unknown_health_and_auth():
    reg = _reg([_w("alpha"), _w("beta")])
    pl = _plan(reg, ["code.edit"], states={"alpha": {"health": "unknown", "auth": "unknown"}}, strict=True)
    assert pl.eligible_executors == ["beta"]
    assert pl.rejected_executors["alpha"].reasons == ["health-unknown", "auth-unknown"]


def test_policy_can_disallow_unknown_health():
    reg = _reg([_w("alpha")], policy={"allow_unknown_health": False})
    pl = _plan(reg, ["code.edit"], states={"alpha": {"health": "unknown"}})
    assert pl.status == "blocked" and pl.rejected_executors["alpha"].reasons == ["health-unknown"]


def test_host_and_locality_filters():
    reg = _reg([_w("alpha", hosts=["msi"]), _w("beta", hosts=["mac"])])
    pl = _plan(reg, ["code.edit"], hosts=("mac",))
    assert pl.executor == "beta" and pl.rejected_executors["alpha"].reasons == ["host-mismatch"]
    pl = _plan(reg, ["code.edit"], localities=("local",))
    assert pl.status == "blocked"
    assert all(r.reasons == ["policy-blocked"] for r in pl.rejected_executors.values())


def test_hard_policy_constraints_override_cost_preference():
    reg = _reg([_w("cheap", cost="free", locality="local", risk="high"),
                _w("safe", risk="low")])
    assert _plan(reg, ["code.edit"]).executor == "cheap"             # cost wins absent constraints
    pl = _plan(reg, ["code.edit"], max_risk="medium")
    assert pl.executor == "safe" and pl.rejected_executors["cheap"].reasons == ["policy-blocked"]
    pl = _plan(reg, ["code.edit"], deny=("cheap",))
    assert pl.executor == "safe"


def test_non_runtime_adoption_never_selected():
    reg = _reg([_w("alpha", integrations={"fut": "supported"}),
                _t("fut", ["web.interact"], adoption="future")])
    pl = _plan(reg, ["web.interact"])
    assert pl.status == "blocked"
    rej = pl.by_capability["web.interact"].rejected["fut"]
    assert rej.reasons == ["policy-blocked"] and "adoption=future" in rej.details[0]


# ------------------------------------------------------------ ranking
def test_cost_preference_ladder():
    reg = _reg([_w("exp", cost="expensive"), _w("met", cost="metered"), _w("sub"),
                _w("free", cost="free", locality="local")])
    pl = _plan(reg, ["code.edit"])
    assert pl.eligible_executors == ["free", "sub", "met", "exp"]
    assert pl.fallbacks == ["sub", "met", "exp"] and pl.reasons == ["cost-preferred"]


def test_locality_breaks_cost_tie_then_latency_then_preference_then_id():
    reg = _reg([_w("cloud1", cost="free"), _w("local1", cost="free", locality="local")])
    assert _plan(reg, ["code.edit"]).reasons == ["local-preferred"]
    reg = _reg([_w("slow", latency="high_latency"), _w("fast")])
    assert _plan(reg, ["code.edit"]).reasons == ["latency-preferred"]
    reg = _reg([_w("bb", preference=1), _w("aa", preference=2)])
    pl = _plan(reg, ["code.edit"])
    assert (pl.executor, pl.reasons) == ("bb", ["preference-order"])
    reg = _reg([_w("bb"), _w("aa")])
    pl = _plan(reg, ["code.edit"])
    assert (pl.executor, pl.reasons) == ("aa", ["id-tiebreak"])


def test_ordering_is_deterministic_regardless_of_declaration_order():
    a = [_w("xx"), _w("yy", cost="free"), _w("zz", cost="metered")]
    p1 = _plan(_reg(a), ["code.edit"]).to_dict()
    p2 = _plan(_reg(list(reversed(a))), ["code.edit"]).to_dict()
    assert p1 == p2 and p1["eligible_executors"] == ["yy", "xx", "zz"]


def test_capability_preference_outranks_cost_and_adds_reason():
    reg = _reg([_w("alpha", integrations={"pw": "supported", "cheap": "supported"}),
                _t("pw", ["web.interact"], cost="existing_subscription"),
                _t("cheap", ["web.interact"])],
               policy={"capability_preferences": {"web.interact": ["pw"]},
                       "capability_reasons": {"web.interact": "browser-deterministic"}})
    pl = _plan(reg, ["web.interact"])
    assert pl.tools == {"web.interact": "pw"} and pl.tool_fallbacks == {"web.interact": ["cheap"]}
    res = pl.by_capability["web.interact"]
    assert res.eligible == ["pw", "cheap"] and res.reasons == ["capability-preferred", "browser-deterministic"]
    assert "browser-deterministic" in pl.reasons


def test_preferred_tool_path_ranks_executor_higher():
    reg = _reg([_w("native", caps=("code.edit", "code.references")),
                _w("viaserena", integrations={"serena": "supported"}),
                _t("serena", ["code.references"])],
               policy={"capability_preferences": {"code.references": ["serena"]}})
    pl = _plan(reg, ["code.references"])
    assert pl.eligible_executors == ["viaserena", "native"] and pl.reasons == ["capability-preferred"]


def test_tool_fallback_when_preferred_tool_unavailable():
    reg = _reg([_w("alpha", integrations={"pw": "supported", "alt": "supported"}),
                _t("pw", ["web.interact"]), _t("alt", ["web.interact"], cost="metered")],
               policy={"capability_preferences": {"web.interact": ["pw", "alt"]}})
    pl = _plan(reg, ["web.interact"], states={"pw": {"available": "absent"}})
    assert pl.tools == {"web.interact": "alt"}
    assert pl.by_capability["web.interact"].rejected["pw"].reasons == ["provider-unavailable"]


# ------------------------------------------------------------ blocked / unknown
def test_unknown_capability_blocks_without_guessing():
    reg = _reg([_w("alpha")])
    pl = _plan(reg, ["code.edit", "code.telepathy"])
    assert (pl.status, pl.exit_state, pl.executor) == ("blocked", "blocked", None)
    assert pl.unknown_capabilities == ["code.telepathy"] and pl.reasons == ["unknown-capability"]
    assert "code.telepathy: unknown-capability" in pl.handoff


def test_no_eligible_provider_is_blocked_handoff():
    reg = _reg([_w("alpha", integrations={"refs": "supported"}), _t("refs", ["code.references"])])
    pl = _plan(reg, ["code.references"], states={"refs": {"available": "absent"}})
    assert pl.status == "blocked" and pl.reasons == ["no-eligible-provider"]
    assert pl.handoff == ["code.references: refs (provider-unavailable)"]
    assert pl.next_step.startswith("human handoff")
    assert pl.eligible_executors == [] and pl.worker is None


def test_explanation_lists_selection_rejection_and_fallbacks():
    reg = _reg([_w("alpha", integrations={"refs": "supported"}), _w("beta"),
                _t("refs", ["code.references"])])
    lines = "\n".join(_plan(reg, ["code.references"]).explain())
    assert "selected executor: alpha [only-eligible-candidate]" in lines
    assert "code.references -> refs" in lines
    assert "rejected executor beta: capability-missing, integration-unknown" in lines
    assert "executor fallbacks: -" in lines


def test_all_reason_codes_come_from_stable_vocabulary():
    reg = _reg([_w("alpha", integrations={"refs": "supported"}), _w("beta", hosts=["msi"]),
                _t("refs", ["code.references"])])
    pl = _plan(reg, ["code.references", "code.edit"], hosts=("mac",))
    codes = set(pl.reasons)
    for r in [*pl.rejected_executors.values(), *(x for res in pl.by_capability.values() for x in res.rejected.values())]:
        codes |= set(r.reasons)
    for res in pl.by_capability.values():
        codes |= set(res.reasons)
    assert codes <= set(R.REJECTION_REASONS) | set(R.SELECTION_REASONS)
