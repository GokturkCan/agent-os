"""R3.1: the backend-neutral SystemOne contract wired into the router's `fastgate` stage.

No decision model is integrated. The default backend is the null backend, which escalates, so
routing is unchanged. Hard policy (risk gate, provider/worker/capability eligibility) always
runs first and SystemOne can only narrow among options policy already approved."""
import copy
import itertools

import pytest

from agentos import cli, dispatch as dispatch_mod, router, systemone as S, telemetry
from agentos import config as C
from agentos.dispatch import dispatch
from evals.test_timeouts import PYTEST

# What the Run 1 router produced for `classification` before R3.1 (verified against the v1.0.0 tag).
RUN1_CLASSIFICATION_TRACE = [
    "fastgate: skip — no usable model (candidates only)",
    "local_primary: skip — no usable model (candidates only)",
    "local_fallback: skip — no usable model (candidates only)",
    "C4: selected claude_subscription via claude_code",
]


def _without_systemone(trace):
    return [t for t in trace if not t.startswith("fastgate: systemone")]


class Spy:
    """Test backend: records requests, then chooses/raises/returns junk as instructed."""
    name = "spy"

    def __init__(self, choose=None, boom=False, junk=False):
        self.requests, self.choose, self.boom, self.junk = [], choose, boom, junk

    def decide(self, request):
        self.requests.append(request)
        if self.boom:
            raise RuntimeError("model crashed")
        if self.junk:
            return {"choice": "codex"}
        choice = self.choose(request) if self.choose else request.eligible_options[0]
        return S.SystemOneResponse((S.Answer("worker", choice, S.Confidence(), "spy-choice"),), False,
                                   "backend-choice", self.name)


def _cfg(cfg, backend):
    data = copy.deepcopy(cfg.data)
    data["routing"]["systemone"] = {"backend": backend}
    return C.Config(root=cfg.root, data=data)


CLS = {"type": "classification"}


# ------------------------------------------------------------ scope guards
def test_r31_adds_no_model_backend(cfg):
    assert set(S.BACKENDS) == {"null", "policy-order"}
    assert cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.models["models"]["laya-mlx"]["status"] == "candidate"
    assert cfg.routing["systemone"]["backend"] == "null"        # reference backend is NOT the default


def test_backend_resolution():
    assert isinstance(S.resolve_backend(), S.NullBackend) and isinstance(S.resolve_backend("null"), S.NullBackend)
    assert isinstance(S.resolve_backend("policy-order"), S.PolicyOrderBackend)
    spy = Spy()
    assert S.resolve_backend(spy) is spy
    for bad in ("laya", "", 42, object()):
        with pytest.raises(ValueError):
            S.resolve_backend(bad)


def test_config_validation_rejects_unregistered_backend(cfg):
    assert C.validate(cfg) == []
    assert C.validate(_cfg(cfg, "policy-order")) == []
    assert any("not a registered backend" in e for e in C.validate(_cfg(cfg, "some-model")))


# ------------------------------------------------------------ A / G: NullBackend preserves behaviour
def test_a_null_backend_preserves_run1_classification_route(cfg):
    d = router.route(cfg, CLS)
    assert (d.stage, d.provider, d.worker, d.exit_state) == ("cloud", "claude_subscription", "claude_code", None)
    assert _without_systemone(d.trace) == RUN1_CLASSIFICATION_TRACE
    assert (d.fallbacks, d.failures) == ([], [])
    s = d.systemone
    assert (s["backend"], s["choice"], s["reason"], s["escalate"]) == ("null", None, "no-backend", True)
    assert s["options"] == ["claude_code", "codex"]
    assert "fastgate: systemone[null] escalated (no-backend); continuing deterministic chain" in d.trace


def test_a_other_task_classes_never_run_systemone(cfg):
    for t in ("coding", "review", "summarization", "research", "knowledge_ingest"):
        d = router.route(cfg, {"type": t})
        assert d.systemone is None and not any("systemone" in x for x in d.trace), t
    assert router.route(cfg, {"type": "coding"}).trace == ["C4: selected claude_subscription via claude_code"]
    assert router.route(cfg, {**CLS, "already_classified": True}).systemone is None


@pytest.mark.parametrize("health", [
    {}, {"providers": {"claude_subscription": False}}, {"workers": {"claude_code": False}},
    {"providers": {"claude_subscription": False, "codex_subscription": False}},
    {"workers": {"claude_code": False, "codex": False}}])
def test_g_unusable_backend_falls_back_deterministically(cfg, health):
    base = router.route(cfg, CLS, health, systemone_backend="null")
    for backend in (_cfg(cfg, "no-such-model"), cfg):                       # unknown name in config / default
        d = router.route(backend, CLS, health)
        assert (d.stage, d.provider, d.worker, d.exit_state) == (base.stage, base.provider, base.worker,
                                                                  base.exit_state)
        assert d.systemone["escalate"] is True
    assert base.exit_state in (None, "blocked")                          # same outcome Run 1 produced, never an error


def test_g_unknown_configured_backend_is_traced_and_ignored(cfg):
    d = router.route(_cfg(cfg, "some-model"), CLS)
    assert any("backend unusable" in t and "using null backend" in t for t in d.trace)
    assert d.worker == "claude_code" and d.systemone["backend"] == "null"


def test_g_no_options_means_escalation_not_a_backend_call(cfg):
    spy = Spy()
    d = router.route(cfg, CLS, {"providers": {"claude_subscription": False, "codex_subscription": False}},
                     systemone_backend=spy)
    assert spy.requests == []                                           # nothing eligible -> backend never asked
    assert (d.exit_state, d.systemone["reason"], d.systemone["options"]) == ("blocked", "no-eligible-options", [])


# ------------------------------------------------------------ B: reference backend
def test_b_policy_order_backend_chooses_first_eligible_option(cfg):
    d = router.route(cfg, CLS, systemone_backend="policy-order")
    s = d.systemone
    assert (s["backend"], s["choice"], s["escalate"], s["reason"]) == ("policy-order", "claude_code", False,
                                                                       "policy-order")
    assert (d.provider, d.worker) == ("claude_subscription", "claude_code")
    assert "fastgate: systemone[policy-order] chose worker claude_code from ['claude_code', 'codex'] (policy-order)" \
        in d.trace
    d = router.route(cfg, CLS, {"providers": {"claude_subscription": False}}, systemone_backend="policy-order")
    assert d.systemone["choice"] == "codex" and (d.provider, d.worker) == ("codex_subscription", "codex")


def test_b_backend_can_be_selected_by_explicit_config(cfg):
    d = router.route(_cfg(cfg, "policy-order"), CLS)
    assert d.systemone["backend"] == "policy-order" and d.systemone["choice"] == "claude_code"


def test_b_valid_choice_narrows_the_next_routing_decision(cfg):
    spy = Spy(choose=lambda r: "codex")                                  # eligible, but not the policy-first worker
    d = router.route(cfg, CLS, systemone_backend=spy)
    assert (d.provider, d.worker, d.exit_state) == ("codex_subscription", "codex", None)
    assert d.systemone["choice"] == "codex" and d.systemone["escalate"] is False


# ------------------------------------------------------------ C: ineligible choices are rejected
@pytest.mark.parametrize("bad", ["opencode", "deepseek_harness", "hermes_delegation", "made-up", "", None])
def test_c_ineligible_backend_choice_is_rejected_and_routing_continues(cfg, bad):
    d = router.route(cfg, CLS, systemone_backend=Spy(choose=lambda r: bad))
    assert (d.provider, d.worker, d.exit_state) == ("claude_subscription", "claude_code", None)
    assert d.systemone["choice"] is None and d.systemone["escalate"] is True
    assert d.systemone["reason"] in ("ineligible-choice", "unanswered-question")


# ------------------------------------------------------------ D: backend failures escalate
@pytest.mark.parametrize("spy", [Spy(boom=True), Spy(junk=True)])
def test_d_backend_exception_or_junk_escalates_without_crashing(cfg, spy):
    d = router.route(cfg, CLS, systemone_backend=spy)
    assert (d.stage, d.worker, d.exit_state) == ("cloud", "claude_code", None)
    assert d.systemone["reason"] == "backend-error" and d.systemone["escalate"] is True
    assert _without_systemone(d.trace) == RUN1_CLASSIFICATION_TRACE


def test_d_failure_while_building_the_request_also_escalates(cfg, monkeypatch):
    monkeypatch.setattr(router, "_eligible_options", lambda *a, **k: (_ for _ in ()).throw(KeyError("boom")))
    d = router.route(cfg, CLS, systemone_backend="policy-order")
    assert (d.worker, d.exit_state) == ("claude_code", None)
    assert d.systemone["reason"] == "backend-error" and any("systemone error (KeyError)" in t for t in d.trace)


# ------------------------------------------------------------ E: human-approval gate precedes SystemOne
@pytest.mark.parametrize("event", [{"risk": "high"}, {"markers": ["payment"]}, {"markers": ["credential_change"]}])
def test_e_high_risk_without_approval_stops_before_systemone(cfg, event):
    spy = Spy()
    d = router.route(cfg, {**CLS, **event}, systemone_backend=spy)
    assert d.exit_state == "human_handoff" and d.requires_human_approval
    assert spy.requests == [] and d.systemone is None                   # backend never consulted


def test_e_with_approval_systemone_still_only_narrows(cfg):
    spy = Spy()
    d = router.route(cfg, {**CLS, "risk": "high", "human_approval_ref": "human:ticket-1"}, systemone_backend=spy)
    assert d.exit_state is None and len(spy.requests) == 1
    assert spy.requests[0].risk == "high"                               # the backend is told, it cannot waive it
    assert d.requires_human_approval is True


# ------------------------------------------------------------ F: capability eligibility is never widened
def test_f_capability_eligible_workers_bound_the_options(cfg):
    spy = Spy(choose=lambda r: "claude_code")                           # tries to pick outside the eligible set
    d = router.route(cfg, {**CLS, "eligible_workers": ["codex"], "required_capabilities": ["code.edit"]},
                     systemone_backend=spy)
    assert spy.requests[0].eligible_options == ("codex",)
    assert spy.requests[0].required_capabilities == ("code.edit",)
    assert d.systemone["escalate"] is True and d.systemone["reason"] == "ineligible-choice"
    assert (d.provider, d.worker) == ("codex_subscription", "codex")    # routing itself also honours eligibility


def test_f_empty_capability_set_means_no_options_and_the_same_outcome_as_run1(cfg):
    spy = Spy()
    d = router.route(cfg, {**CLS, "eligible_workers": []}, systemone_backend=spy)
    plain = router.route(cfg, {"type": "classification", "eligible_workers": []}, systemone_backend="null")
    assert spy.requests == [] and d.exit_state == plain.exit_state == "blocked"
    assert d.systemone["reason"] == "no-eligible-options"


HEALTHS = [{}, {"providers": {"claude_subscription": False}}, {"providers": {"codex_subscription": False}},
           {"workers": {"claude_code": False}}, {"workers": {"codex": False}}]
ELIGIBLE = [None, ["claude_code"], ["codex"], ["claude_code", "codex"], ["opencode"], []]


@pytest.mark.parametrize("health,eligible", list(itertools.product(HEALTHS, ELIGIBLE)))
def test_f_options_never_widen_and_every_option_is_routable(cfg, health, eligible):
    event = {**CLS, **({} if eligible is None else {"eligible_workers": eligible})}
    spy = Spy()
    router.route(cfg, event, health, systemone_backend=spy)
    options = list(spy.requests[0].eligible_options) if spy.requests else []
    allowed = set(cfg.routing["task_classes"]["classification"]["workers"])
    assert set(options) <= allowed and (eligible is None or set(options) <= set(eligible))
    assert "opencode" not in options
    for opt in options:                                                  # narrowing to ANY option never blocks
        d = router.route(cfg, event, health, systemone_backend=Spy(choose=lambda r, o=opt: o))
        assert d.exit_state is None and d.worker == opt, (health, eligible, opt, d.trace)


def test_f_unavailable_or_unenforceable_workers_are_never_options(cfg):
    spy = Spy()
    router.route(cfg, CLS, {"workers": {"claude_code": False, "codex": False}}, systemone_backend=spy)
    assert spy.requests == []
    enabled = copy.deepcopy(cfg.data)
    enabled["workers"]["workers"]["opencode"]["status"] = "available"
    enabled["routing"]["task_classes"]["classification"]["workers"].append("opencode")
    c2 = C.Config(root=cfg.root, data=enabled)
    spy = Spy()
    router.route(c2, CLS, systemone_backend=spy)
    assert "opencode" not in spy.requests[0].eligible_options           # launch cannot enforce a profile


def test_unroutable_choice_reroutes_without_narrowing(cfg, monkeypatch):
    """Safety valve: if a narrowed route were ever blocked, policy routes as if SystemOne escalated."""
    monkeypatch.setattr(router, "_eligible_options", lambda *a, **k: ["codex", "deepseek_harness"])
    d = router.route(cfg, CLS, systemone_backend=Spy(choose=lambda r: "deepseek_harness"))
    assert (d.stage, d.worker, d.exit_state) == ("cloud", "claude_code", None)
    assert d.systemone["reason"] == "unroutable-choice" and d.systemone["choice"] is None
    assert any("re-routed deterministically without narrowing" in t for t in d.trace)


# ------------------------------------------------------------ SystemOne stays narrow
def test_request_is_typed_and_contains_no_free_text_or_tools(cfg):
    spy = Spy()
    router.route(cfg, {**CLS, "prompt": "do secret thing", "token": "sk-123"}, systemone_backend=spy)
    req = spy.requests[0]
    assert [q.id for q in req.questions] == ["worker"] and req.questions[0].kind == "choose"
    assert dict(req.state) == {"task_class": "classification", "stage": "fastgate"}
    assert "secret" not in repr(req) and "sk-123" not in repr(req)
    assert req.task_type == "classification" and req.risk == "low"


# ------------------------------------------------------------ telemetry (additive)
def test_telemetry_fields_are_additive_and_simple(cfg):
    assert {"systemone_backend", "systemone_choice", "systemone_reason", "systemone_escalate"} <= telemetry.FIELDS
    assert cli.main(["route", "classification", "--record"]) == 0
    rec = telemetry.read_all()[-1]
    assert (rec["systemone_backend"], rec["systemone_choice"], rec["systemone_reason"],
            rec["systemone_escalate"]) == ("null", None, "no-backend", True)
    assert cli.main(["route", "coding", "--record"]) == 0
    rec = telemetry.read_all()[-1]
    assert [rec[k] for k in ("systemone_backend", "systemone_choice", "systemone_reason",
                             "systemone_escalate")] == [None] * 4        # step did not run -> null
    assert all(isinstance(v, (str, bool, type(None))) for k, v in rec.items() if k.startswith("systemone"))


def test_dispatch_records_systemone_on_the_trace_record(cfg, fixture_repo, tmp_path):
    noop = lambda launch, **kw: {"returncode": 0, "latency_ms": 1.0}
    res = dispatch(cfg, task_id="s1-task", task_type="classification", repo=fixture_repo, prompt="x",
                   verify=PYTEST, runner=noop, worktree_root=tmp_path / "wts")
    assert res["worker"] == "claude_code"                                # routing and execution unchanged
    rec = telemetry.read_all()[-1]
    assert rec["systemone_backend"] == "null" and rec["systemone_reason"] == "no-backend"
    assert rec["systemone_escalate"] is True
