"""R3.2C: authoritative option metadata, abstention and the richer request formulation.

Safety properties pinned here: metadata can describe options but never introduce one; unknown or
oversized or secret-looking metadata fails closed; abstaining is an escalation, never a choice;
the human-approval gate and the null default are unchanged; and the legacy (bare-id) wire format
and worker behaviour stay exactly as they were in R3.2B."""
import copy
import importlib.util
import json
import sys

import pytest

from agentos import config as C
from agentos import router
from agentos import systemone as S
from agentos import systemone_adapter as A
from agentos import systemone_options as O

CLS = {"type": "classification"}
LAYA_WORKER = C.REPO_ROOT / "agentos" / "systemone_workers" / "laya_worker.py"


def _req(options=("claude_code", "codex"), **kw):
    kw.setdefault("state", {"task_class": "classification", "stage": "fastgate"})
    return S.SystemOneRequest(task_type="classification", eligible_options=tuple(options),
                              questions=(S.Question("worker", "choose", "Which worker?"),), **kw)


@pytest.fixture(autouse=True)
def _clean():
    yield
    A.close_all()


# ------------------------------------------------------------ the builder: authoritative, never invented
def test_metadata_comes_from_config_and_registry(cfg):
    info = O.build(cfg, ["claude_code", "codex", "deepseek_harness"], ("code.references",))
    assert info["claude_code"]["roles"] == cfg.workers["workers"]["claude_code"]["roles"]
    assert info["codex"]["roles"] == cfg.workers["workers"]["codex"]["roles"]
    assert info["claude_code"]["access"] == info["codex"]["access"] == "harness"
    assert info["deepseek_harness"]["access"] == "api" and info["deepseek_harness"]["interactive"] is False
    assert info["claude_code"]["cost"] == "existing_subscription" and "cost" not in info["deepseek_harness"]
    assert info["claude_code"]["missing"] == [] and info["codex"]["missing"] == ["code.references"]
    assert "missing" not in info["deepseek_harness"]            # not a registered executor: nothing is invented


def test_missing_capabilities_use_the_capability_plane_integration_logic(cfg):
    m = lambda caps: {k: v["missing"] for k, v in O.build(cfg, ["claude_code", "codex"], caps).items()}
    assert m(("code.edit", "code.test")) == {"claude_code": [], "codex": []}                 # native to both
    assert m(("web.docs_lookup",)) == {"claude_code": [], "codex": ["web.docs_lookup"]}      # context7: claude only
    assert m(("web.interact", "devops.github")) == {"claude_code": [], "codex": ["web.interact"]}
    rea = ["reverse_engineering.static_analysis"]
    assert m(rea) == {"claude_code": rea, "codex": rea}                                       # rea integration unknown
    assert m(("code.telepathy",)) == {"claude_code": ["code.telepathy"], "codex": ["code.telepathy"]}


def test_ids_that_are_not_configured_workers_get_no_metadata(cfg):
    info = O.build(cfg, ["claude_code", "not_a_worker", "hermes_delegation"], ())
    assert "not_a_worker" not in info and set(info) <= {"claude_code", "hermes_delegation"}


def test_metadata_has_no_free_text_and_only_allowlisted_fields(cfg):
    for w in cfg.workers["workers"]:
        for field, value in O.build(cfg, [w], ("code.edit",)).get(w, {}).items():
            assert field in A.OPTION_FIELDS, field                                           # no `note`, no paths
            texts = value if isinstance(value, list) else [value]
            assert all(isinstance(t, (str, bool)) for t in texts)
    blob = json.dumps(O.build(cfg, list(cfg.workers["workers"]), ("code.edit",)))
    assert "Launch wrapper" not in blob and "/" not in blob and "~" not in blob


def test_builder_degrades_to_static_facts_without_a_registry(cfg, monkeypatch):
    monkeypatch.setattr(O, "_registry", lambda c: None)
    info = O.build(cfg, ["claude_code", "codex"], ("code.references",))
    assert info["claude_code"]["roles"] and "missing" not in info["claude_code"] and "cost" not in info["claude_code"]


# ------------------------------------------------------------ sanitization: validate, size-cap, never widen
def test_metadata_for_unoffered_ids_is_dropped_and_cannot_introduce_an_option():
    out = A.sanitize_option_info({"claude_code": {"access": "harness"}, "opencode": {"access": "harness"}},
                                 ["claude_code", "codex"])
    assert out == {"claude_code": {"access": "harness"}}
    req = _req(option_info={"opencode": {"roles": ["overflow"]}, "claude_code": {"access": "harness"}})
    p = A.build_payload(req, req.questions[0])
    assert p["options"] == ["claude_code", "codex"] and set(p["option_info"]) == {"claude_code"}
    assert "opencode" not in json.dumps(p)


@pytest.mark.parametrize("bad,reason", [
    ({"claude_code": {"note": "free text"}}, "unsupported-question"),                         # unknown field
    ({"claude_code": {"roles": "architecture"}}, "unsupported-question"),                     # str where list expected
    ({"claude_code": {"interactive": "no"}}, "unsupported-question"),                         # str where bool expected
    ({"claude_code": {"access": "has spaces"}}, "unsupported-question"),
    ({"claude_code": {"access": "x" * 65}}, "unsupported-question"),
    ({"claude_code": {"roles": ["fine", "bad role"]}}, "unsupported-question"),
    ({"claude_code": {"roles": [1, 2]}}, "unsupported-question"),
    ({"claude_code": {"missing": [f"cap.n{i}" for i in range(9)]}}, "state-too-large"),       # never truncate `missing`
    ({"claude_code": {"access": "sk-ABCDEF1234567890SECRET"}}, "unsupported-question"),       # secret-looking
    ({"claude_code": {"roles": ["token=abcdef123456"]}}, "unsupported-question"),
    ({"claude_code": "harness"}, "unsupported-question"),
    ("not a mapping", "unsupported-question"),
])
def test_invalid_oversized_or_secret_metadata_fails_closed(bad, reason):
    with pytest.raises(A.AdapterReject) as e:
        A.sanitize_option_info(bad, ["claude_code", "codex"])
    assert e.value.reason == reason


def test_total_payload_stays_inside_the_4096_byte_cap():
    many = {f"opt{i:02d}": {"roles": ["role_aaaaaaaaaaaaaaaaaaaa"] * 6, "missing": ["cap.aaaaaaaaaaaaaaaaaaaa"] * 8,
                            "access": "harness", "latency": "network"} for i in range(12)}
    req = S.SystemOneRequest("t", (S.Question("worker", "choose", "Which?"),), eligible_options=tuple(many),
                             option_info=many)
    with pytest.raises(A.AdapterReject) as e:
        A.build_payload(req, req.questions[0])
    assert e.value.reason == "state-too-large"
    assert A.AdapterBackend("x", _NullRuntime()).decide(req).reason_code == "state-too-large"   # and via the backend


class _NullRuntime:
    name = "null"

    def ask(self, payload, timeout):
        raise AssertionError("the runtime must not be called for an invalid request")

    def close(self):
        pass


def test_real_metadata_fits_comfortably(cfg):
    info = O.build(cfg, ["claude_code", "codex", "deepseek_harness"], ("code.references", "web.interact", "devops.github"))
    req = _req(options=("claude_code", "codex", "deepseek_harness"), option_info=info)
    size = len(json.dumps(A.build_payload(req, req.questions[0]), separators=(",", ":")).encode())
    assert size < A.MAX_PAYLOAD_BYTES // 2


def test_legacy_requests_keep_the_exact_legacy_wire_format():
    p = A.build_payload(_req(), _req().questions[0])
    assert set(p) == {"v", "question", "options", "state"}                    # no option_info / allow_abstain keys
    assert p["v"] == 1


def test_payload_never_carries_secrets_from_state_or_metadata():
    secret = "sk-ABCDEF1234567890SECRET"
    req = _req(state={"note": f"Authorization: Bearer {secret}"}, option_info={"claude_code": {"access": "harness"}})
    assert secret not in json.dumps(A.build_payload(req, req.questions[0]))


# ------------------------------------------------------------ abstention is an escalation, never a choice
PAYLOAD = {"v": 1, "question": {"id": "worker", "kind": "choose", "prompt": ""}, "options": ["claude_code", "codex"],
           "state": {}}


def test_abstain_is_an_escalation_when_allowed():
    with pytest.raises(A.AdapterReject) as e:
        A.parse_reply({"v": 1, "id": "worker", "abstain": True, "confidence": 0.9}, {**PAYLOAD, "allow_abstain": True})
    assert e.value.reason == "backend-abstained"


@pytest.mark.parametrize("reply,payload", [
    ({"v": 1, "id": "worker", "abstain": True}, PAYLOAD),                                               # not allowed
    ({"v": 1, "id": "worker", "abstain": True, "choice": "codex"}, {**PAYLOAD, "allow_abstain": True}),  # both
])
def test_abstain_without_permission_or_alongside_a_choice_is_malformed(reply, payload):
    with pytest.raises(A.AdapterReject) as e:
        A.parse_reply(reply, payload)
    assert e.value.reason == "malformed-output"


STUB = r'''
import json, sys
mode = sys.argv[1]
print(json.dumps({"ready": True, "runtime": {}}), flush=True)
for line in sys.stdin:
    req = json.loads(line); qid = req["question"]["id"]
    if mode == "abstain": reply = {"v": 1, "id": qid, "abstain": True, "confidence": 0.6}
    elif mode == "echo": reply = {"v": 1, "id": qid, "choice": req["options"][0], "confidence": 0.5,
                                  "seen_option_info": sorted(req.get("option_info", {})), "abstain_ok": req.get("allow_abstain", False)}
    print(json.dumps(reply), flush=True)
'''


@pytest.fixture
def stub(tmp_path):
    path = tmp_path / "stub.py"
    path.write_text(STUB)

    def make(mode):
        rt = A.SubprocessJsonRuntime([sys.executable, str(path), mode], name=mode, cooldown=0, startup_timeout=5)
        return A.AdapterBackend(f"stub-{mode}", rt, timeout=1.0)
    return make


def test_abstaining_backend_escalates_with_its_own_reason(stub):
    resp = stub("abstain").decide(_req(allow_abstain=True))
    assert resp.escalate and resp.answers == () and resp.reason_code == "backend-abstained"
    assert S.system_one(_req(allow_abstain=True), stub("abstain")).escalate


def test_abstain_reply_to_a_request_that_did_not_allow_it_is_malformed(stub):
    assert stub("abstain").decide(_req()).reason_code == "malformed-output"


def test_worker_that_ignores_new_fields_keeps_working(stub):
    resp = stub("echo").decide(_req(option_info={"claude_code": {"access": "harness"}}, allow_abstain=True))
    assert not resp.escalate and resp.answers[0].choice == "claude_code"       # extra v1 keys are additive


# ------------------------------------------------------------ the Laya worker's rendering
@pytest.fixture(scope="module")
def laya_worker():
    spec = importlib.util.spec_from_file_location("laya_worker_under_test", LAYA_WORKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                     # imports only the stdlib; laya_mlx is loaded inside main()
    return mod


def test_legacy_payload_renders_exactly_the_r32b_criteria(laya_worker):
    legacy = {"options": ["claude_code", "codex"], "state": {}, "question": {"id": "worker"}}
    assert laya_worker.criteria_for(legacy) == (["claude_code", "codex"], None)    # a plain list of ids, as before


def test_rendering_is_deterministic_structured_text_only(laya_worker):
    req = {"options": ["claude_code", "deepseek_harness"],
           "option_info": {"claude_code": {"roles": ["architecture", "review"], "access": "harness",
                                           "cost": "existing_subscription", "missing": []},
                           "deepseek_harness": {"roles": ["background_coding_escalation"], "access": "api",
                                                "interactive": False, "missing": ["code.references"]}}}
    criteria, abstain = laya_worker.criteria_for(req)
    assert abstain is None and list(criteria) == ["claude_code", "deepseek_harness"]
    assert criteria["claude_code"] == ("roles: architecture, review; access: harness; cost: existing_subscription; "
                                       "missing required capabilities: none")
    assert criteria["deepseek_harness"] == ("roles: background_coding_escalation; background only, not interactive; "
                                            "access: api; missing required capabilities: code.references")
    assert laya_worker.criteria_for(req) == (criteria, None)                       # same input, same text


def test_abstain_label_is_offered_last_and_never_collides_with_an_option(laya_worker):
    req = {"options": ["claude_code", "codex"], "option_info": {}, "allow_abstain": True}
    criteria, label = laya_worker.criteria_for(req)
    assert label == "none_fits" and list(criteria)[-1] == label and set(criteria) == {"claude_code", "codex", label}
    clash = {"options": ["none_fits", "codex"], "allow_abstain": True}
    criteria, label = laya_worker.criteria_for(clash)
    assert label == "none_fits_" and "none_fits" in criteria and label in criteria      # a real option keeps its name


def test_option_without_metadata_falls_back_to_its_own_id(laya_worker):
    criteria, _ = laya_worker.criteria_for({"options": ["a", "b"], "option_info": {"a": {"access": "api"}}})
    assert criteria == {"a": "access: api", "b": "b"}


# ------------------------------------------------------------ the router: advisory context, policy unchanged
class Spy:
    name = "spy"

    def __init__(self, choose=None):
        self.requests, self.choose = [], choose

    def decide(self, request):
        self.requests.append(request)
        pick = self.choose(request) if self.choose else request.eligible_options[0]
        return S.SystemOneResponse((S.Answer("worker", pick, S.Confidence(), "spy-choice"),), False, "backend-choice", "spy")


def test_router_sends_authoritative_metadata_for_exactly_the_offered_options(cfg):
    spy = Spy()
    router.route(cfg, {**CLS, "required_capabilities": ["code.references"]}, systemone_backend=spy)
    req = spy.requests[0]
    assert set(req.eligible_options) == {"claude_code", "codex"} and set(req.option_info) == {"claude_code", "codex"}
    assert req.option_info["codex"]["missing"] == ["code.references"] and req.option_info["claude_code"]["missing"] == []
    assert req.questions[0].prompt == O.QUESTION_PROMPT and req.allow_abstain is False       # abstain is opt-in only


def test_router_metadata_follows_capability_narrowing_and_never_widens(cfg):
    spy = Spy()
    router.route(cfg, {**CLS, "eligible_workers": ["codex"]}, systemone_backend=spy)
    assert spy.requests[0].eligible_options == ("codex",) and set(spy.requests[0].option_info) == {"codex"}


def test_metadata_cannot_make_an_ineligible_worker_a_valid_choice(cfg):
    spy = Spy(choose=lambda r: "opencode")                               # tries to use a disabled worker
    d = router.route(cfg, CLS, systemone_backend=spy)
    assert d.systemone["reason"] == "ineligible-choice" and d.systemone["escalate"] is True
    assert d.worker == "claude_code"                                     # deterministic policy decides


def test_failure_to_build_metadata_never_fails_routing(cfg, monkeypatch):
    monkeypatch.setattr(O, "build", lambda *a, **k: (_ for _ in ()).throw(KeyError("registry exploded")))
    spy = Spy()
    d = router.route(cfg, CLS, systemone_backend=spy)
    assert spy.requests[0].option_info == {} and d.worker == spy.requests[0].eligible_options[0]
    assert d.exit_state is None


def test_high_risk_approval_gate_still_precedes_the_backend(cfg):
    spy = Spy()
    d = router.route(cfg, {**CLS, "risk": "high"}, systemone_backend=spy)
    assert d.exit_state == "human_handoff" and spy.requests == [] and d.systemone is None
    d = router.route(cfg, {**CLS, "risk": "high", "human_approval_ref": "human:ok"}, systemone_backend=spy)
    assert d.exit_state is None and spy.requests[0].risk == "high"


def test_null_default_routes_exactly_as_before_with_the_new_fields(cfg):
    assert cfg.routing["systemone"]["backend"] == "null"
    d = router.route(cfg, CLS)
    assert d.systemone["backend"] == "null" and d.systemone["reason"] == "no-backend"
    assert (d.stage, d.provider, d.worker, d.exit_state) == ("cloud", "claude_subscription", "claude_code", None)
    assert A._CACHE == {}


def test_safe_fallback_when_an_adapter_backend_fails_with_metadata_present(cfg, tmp_path):
    path = tmp_path / "boom.py"
    path.write_text("import sys\nsys.exit(3)\n")
    data = copy.deepcopy(cfg.data)
    data["systemone"]["backends"]["boom"] = {"adapter": "subprocess_json", "argv": [sys.executable, str(path)],
                                             "timeout_seconds": 0.5, "startup_timeout_seconds": 3, "cooldown_seconds": 0}
    data["routing"]["systemone"] = {"backend": "boom"}
    base = router.route(cfg, CLS)
    d = router.route(C.Config(root=cfg.root, data=data), CLS)
    assert d.systemone["reason"] == "backend-unavailable" and (d.worker, d.exit_state) == (base.worker, None)


def test_confidence_stays_raw_and_is_not_a_threshold(cfg):
    spy = Spy()
    d = router.route(cfg, CLS, systemone_backend=Spy(choose=lambda r: r.eligible_options[-1]))
    assert d.systemone["confidence_kind"] in ("none", "raw")
    assert S.ConfidencePolicy(0.0, "any").accepts(S.Confidence(0.99, "raw")) == (False, "uncalibrated-confidence")
    assert not hasattr(router, "CONFIDENCE_THRESHOLD")
