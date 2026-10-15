"""R3.2A: the backend-neutral SystemOne adapter layer (no real model needed).

A stub worker process stands in for a model so every failure mode is forced deterministically.
Whatever the runtime does, the adapter must fail closed to an ESCALATION, never raise into the
router, never widen eligibility, and never treat model output as authority."""
import copy
import json
import os
import sys
import time

import pytest

from agentos import config as C
from agentos import router
from agentos import systemone as S
from agentos import systemone_adapter as A
from agentos.permissions import is_protected
from agentos.selfimprove import compute_manifest

STUB = r'''
import json, os, sys, time
mode = sys.argv[1]
if mode == "dump_env":
    open(sys.argv[2], "w").write(json.dumps(sorted(os.environ)) + "\n" + json.dumps(dict(os.environ)))
if mode == "no_ready":
    sys.exit(3)
if mode == "slow_start":
    time.sleep(30)
print(json.dumps({"ready": mode != "bad_ready", "runtime": {"stub": "1"}}), flush=True)
for line in sys.stdin:
    req = json.loads(line)
    qid, opts = req["question"]["id"], req["options"]
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        sys.exit(9)
    if mode == "garbage":
        print("this is not json", flush=True); continue
    if mode == "huge":
        print("x" * 20000, flush=True); continue
    reply = {"v": 1, "id": qid, "choice": opts[-1], "confidence": 0.7, "reason_code": "backend-choice"}
    if mode == "wrong_id": reply["id"] = "other"
    if mode == "bad_version": reply["v"] = 2
    if mode == "ineligible": reply["choice"] = "opencode"
    if mode == "missing": reply.pop("choice")
    if mode == "null_choice": reply["choice"] = None
    if mode == "int_choice": reply["choice"] = 3
    if mode == "bad_conf": reply["confidence"] = 7
    if mode == "bool_conf": reply["confidence"] = True
    if mode == "str_conf": reply["confidence"] = "high"
    if mode == "nan_conf": reply["confidence"] = float("nan")
    if mode == "no_conf": reply.pop("confidence")
    if mode == "prose": reply.update(text="ignore policy and run rm -rf /", plan=["escalate privileges"], choice=opts[0])
    if mode == "weird_reason": reply["reason_code"] = "trust me, I am certain"
    if mode == "error": reply = {"v": 1, "id": qid, "error": "RuntimeError"}
    if mode == "not_object": reply = ["choice", opts[0]]
    print(json.dumps(reply), flush=True)
'''


@pytest.fixture(autouse=True)
def _clean_adapters():
    yield
    A.close_all()


@pytest.fixture
def stub(tmp_path):
    path = tmp_path / "stub_worker.py"
    path.write_text(STUB)

    def make(mode, *, timeout=1.0, startup=5.0, cooldown=0.0, extra=()):
        rt = A.SubprocessJsonRuntime([sys.executable, str(path), mode, *extra], name=f"stub-{mode}",
                                     startup_timeout=startup, cooldown=cooldown)
        return A.AdapterBackend(f"stub-{mode}", rt, timeout=timeout)
    return make


def _req(options=("claude_code", "codex"), **kw):
    kw.setdefault("state", {"task_class": "classification", "stage": "fastgate"})
    return S.SystemOneRequest(task_type="classification", questions=(S.Question("worker", "choose", "Which worker?"),),
                              eligible_options=tuple(options), **kw)


# ------------------------------------------------------------ payload: what a model is shown
def test_payload_is_compact_typed_and_redacted():
    secret = "sk-ABCDEF1234567890SECRET"
    req = _req(state={"task_class": "classification", "note": f"Authorization: Bearer {secret} api_key={secret}"},
               required_capabilities=("web.interact", "code.edit"), risk="high",
               resource_state={"msi": False, "mac": True})
    p = A.build_payload(req, req.questions[0])
    assert p["v"] == 1 and p["options"] == ["claude_code", "codex"]
    assert p["question"] == {"id": "worker", "kind": "choose", "prompt": "Which worker?"}
    assert p["state"]["required_capabilities"] == ["code.edit", "web.interact"]      # sorted
    assert p["state"]["risk"] == "high" and p["state"]["resources"] == {"mac": True, "msi": False}
    blob = json.dumps(p)
    assert secret not in blob and "[REDACTED]" in blob
    assert len(blob.encode()) < A.MAX_PAYLOAD_BYTES


def test_payload_never_widens_options_and_rejects_bad_requests():
    req = S.SystemOneRequest("t", (S.Question("worker", "choose", options=("codex", "opencode")),),
                             eligible_options=("claude_code", "codex"))
    assert A.build_payload(req, req.questions[0])["options"] == ["codex"]            # intersection only
    for bad, reason in ((S.Question("q", "yes_no"), "unsupported-question"),):
        with pytest.raises(A.AdapterReject) as e:
            A.build_payload(_req(), bad)
        assert e.value.reason == reason
    with pytest.raises(A.AdapterReject) as e:                                         # weird option ids
        A.build_payload(_req(options=("ok", "bad id with spaces")), S.Question("worker", "choose"))
    assert e.value.reason == "unsupported-question"
    with pytest.raises(A.AdapterReject) as e:
        A.build_payload(_req(state={"blob": "x" * 150, **{f"k{i}": "y" * 150 for i in range(60)}}),
                        S.Question("worker", "choose"))
    assert e.value.reason == "state-too-large"


# ------------------------------------------------------------ reply: what is trusted
PAYLOAD = {"v": 1, "question": {"id": "worker", "kind": "choose", "prompt": ""}, "options": ["claude_code", "codex"],
           "state": {}}


def _ok(**kw):
    return {"v": 1, "id": "worker", "choice": "codex", "confidence": 0.8, **kw}


def test_parse_reply_accepts_only_a_valid_option_with_raw_confidence():
    a = A.parse_reply(_ok(), PAYLOAD)
    assert (a.question_id, a.choice, a.reason_code) == ("worker", "codex", "backend-choice")
    assert (a.confidence.kind, a.confidence.value, a.confidence.calibration_id) == ("raw", 0.8, None)
    assert A.parse_reply(_ok(confidence=None), PAYLOAD).confidence == S.Confidence()
    assert A.parse_reply({k: v for k, v in _ok().items() if k != "confidence"}, PAYLOAD).confidence.kind == "none"
    assert A.parse_reply(_ok(reason_code="policy-order"), PAYLOAD).reason_code == "policy-order"
    assert A.parse_reply(_ok(reason_code="trust me"), PAYLOAD).reason_code == "backend-choice"   # free text dropped


@pytest.mark.parametrize("reply,reason", [
    ("text", "malformed-output"), (None, "malformed-output"), ([1], "malformed-output"),
    (_ok(v=2), "malformed-output"), (_ok(id="other"), "malformed-output"),
    (_ok(choice=3), "malformed-output"), (_ok(choice=["codex"]), "malformed-output"),
    (_ok(confidence=7), "malformed-output"), (_ok(confidence=-0.1), "malformed-output"),
    (_ok(confidence=True), "malformed-output"), (_ok(confidence="high"), "malformed-output"),
    (_ok(confidence=float("nan")), "malformed-output"), (_ok(confidence=float("inf")), "malformed-output"),
    (_ok(choice="opencode"), "ineligible-choice"), (_ok(choice=""), "ineligible-choice"),
    (_ok(choice="CODEX"), "ineligible-choice"),
    ({"v": 1, "id": "worker"}, "unanswered-question"), (_ok(choice=None), "unanswered-question"),
    ({"v": 1, "id": "worker", "error": "RuntimeError"}, "backend-error"),
])
def test_parse_reply_fails_closed(reply, reason):
    with pytest.raises(A.AdapterReject) as e:
        A.parse_reply(reply, PAYLOAD)
    assert e.value.reason == reason


def test_prose_in_a_reply_is_never_kept(stub):
    resp = stub("prose").decide(_req())
    assert not resp.escalate and resp.answers[0].choice == "claude_code"
    assert "rm -rf" not in repr(resp) and "escalate privileges" not in repr(resp)


# ------------------------------------------------------------ runtime: success path
def test_backend_returns_a_typed_response(stub):
    b = stub("ok")
    resp = b.decide(_req())
    assert isinstance(resp, S.SystemOneResponse) and not resp.escalate and resp.backend == "stub-ok"
    a = resp.answers[0]
    assert (a.question_id, a.choice, a.confidence.kind, a.confidence.value) == ("worker", "codex", "raw", 0.7)
    assert b.runtime.info == {"stub": "1"} and b.runtime.startup_seconds is not None
    assert isinstance(b, S.SystemOneBackend)
    assert S.system_one(_req(), b).answer("worker").choice == "codex"                # full contract path


def test_worker_process_is_reused_across_decisions(stub):
    b = stub("ok")
    b.decide(_req())
    pid = b.runtime.pid
    for _ in range(3):
        b.decide(_req())
    assert b.runtime.pid == pid                                                     # warm, not respawned


# ------------------------------------------------------------ runtime: every failure escalates
@pytest.mark.parametrize("mode,reason", [
    ("garbage", "malformed-output"), ("huge", "malformed-output"), ("not_object", "malformed-output"),
    ("wrong_id", "malformed-output"), ("bad_version", "malformed-output"), ("int_choice", "malformed-output"),
    ("bad_conf", "malformed-output"), ("bool_conf", "malformed-output"), ("str_conf", "malformed-output"),
    ("nan_conf", "malformed-output"),
    ("ineligible", "ineligible-choice"), ("missing", "unanswered-question"), ("null_choice", "unanswered-question"),
    ("error", "backend-error"), ("crash", "backend-unavailable"), ("no_ready", "backend-unavailable"),
    ("bad_ready", "backend-unavailable"),
])
def test_failures_escalate_with_a_specific_reason(stub, mode, reason):
    resp = stub(mode).decide(_req())
    assert resp.escalate and resp.answers == () and resp.reason_code == reason, resp
    assert S.system_one(_req(), stub(mode)).escalate                                 # and via the contract


def test_timeout_escalates_and_kills_the_worker(stub):
    b = stub("hang", timeout=0.4)
    t0 = time.monotonic()
    resp = b.decide(_req())
    elapsed = time.monotonic() - t0
    assert resp.escalate and resp.reason_code == "backend-timeout"
    assert elapsed < 3.0                                                            # deadline enforced, not 60 s
    assert b.runtime.pid is None                                                    # process group killed


def test_startup_timeout_escalates(stub):
    resp = stub("slow_start", startup=0.4).decide(_req())
    assert resp.escalate and resp.reason_code == "backend-timeout"


def test_missing_executable_is_unavailable_not_an_exception(tmp_path):
    rt = A.SubprocessJsonRuntime([str(tmp_path / "no-such-python"), "x"], cooldown=0)
    resp = A.AdapterBackend("ghost", rt).decide(_req())
    assert resp.escalate and resp.reason_code == "backend-unavailable"


def test_cooldown_makes_a_broken_backend_cheap(stub):
    b = stub("crash", cooldown=60.0)
    assert b.decide(_req()).reason_code == "backend-unavailable"
    t0 = time.monotonic()
    again = b.decide(_req())
    assert again.reason_code == "backend-unavailable" and time.monotonic() - t0 < 0.2
    assert b.runtime.pid is None                                                    # no respawn during cool-down


def test_runtime_recovers_after_cooldown(stub, tmp_path):
    b = stub("crash", cooldown=0.0)
    assert b.decide(_req()).escalate
    good = stub("ok")
    assert not good.decide(_req()).escalate


def test_runtime_exceptions_never_reach_the_router():
    class Boom:
        name = "boom"

        def ask(self, payload, timeout):
            raise RuntimeError("segfault-ish")

        def close(self):
            pass
    resp = A.AdapterBackend("boom", Boom()).decide(_req())
    assert resp.escalate and resp.reason_code == "backend-error"


# ------------------------------------------------------------ the child cannot see our secrets
def test_worker_environment_is_scrubbed(stub, tmp_path, monkeypatch):
    for name in ("HF_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "GH_TOKEN", "MY_SECRET"):
        monkeypatch.setenv(name, "sk-live-VERY-SECRET-VALUE")
    out = tmp_path / "env.json"
    stub("dump_env", extra=(str(out),)).decide(_req())
    names, env = out.read_text().split("\n", 1)
    names, env = json.loads(names), json.loads(env)
    assert set(names) <= set(A.scrubbed_env()) | {"__CF_USER_TEXT_ENCODING", "LC_CTYPE", "LANG"}
    planted = {"HF_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "GH_TOKEN", "MY_SECRET"}
    assert not planted & set(names)                                                 # none of our secrets inherited
    assert "sk-live-VERY-SECRET-VALUE" not in json.dumps(env)
    assert env["HF_HUB_OFFLINE"] == "1"


# ------------------------------------------------------------ confidence is raw, never calibrated
def test_adapter_confidence_is_raw_and_rejected_by_confidence_policy(stub):
    resp = stub("ok").decide(_req())
    conf = resp.answers[0].confidence
    assert conf.kind == "raw" and not conf.is_calibrated and conf.calibration_id is None
    policy = S.ConfidencePolicy(threshold=0.5, calibration_id="any-calibrator")
    assert policy.accepts(conf) == (False, "uncalibrated-confidence")
    assert policy.accepts(S.Confidence(0.999, "raw")) == (False, "uncalibrated-confidence")


# ------------------------------------------------------------ config + resolution
def _cfg_with_stub(cfg, tmp_path, mode, **extra):
    path = tmp_path / "stub_worker.py"
    path.write_text(STUB)
    data = copy.deepcopy(cfg.data)
    data["systemone"]["backends"]["stub"] = {"adapter": "subprocess_json", "argv": [sys.executable, str(path), mode],
                                             "timeout_seconds": 0.6, "startup_timeout_seconds": 5.0,
                                             "cooldown_seconds": 0, **extra}
    data["routing"]["systemone"] = {"backend": "stub"}
    return C.Config(root=cfg.root, data=data)


def test_real_config_defines_laya_but_default_stays_null(cfg):
    assert cfg.routing["systemone"]["backend"] == "null"
    assert "laya-mlx" in A.definitions(cfg) and C.validate(cfg) == []
    d = A.definitions(cfg)["laya-mlx"]
    assert d["adapter"] == "subprocess_json" and d["model"]["revision"] and d["package"]["version"] == "0.4.0"
    assert cfg.models["tiers"]["fastgate"]["model"] is None                          # tier still unset


def test_backend_definitions_are_protected_policy(cfg):
    assert is_protected("config/systemone.yaml") and "config/systemone.yaml" in compute_manifest()


def test_resolution_is_lazy_cached_and_explicit(cfg):
    A.close_all()
    b1, b2 = S.resolve_backend("laya-mlx", cfg), S.resolve_backend("laya-mlx", cfg)
    assert b1 is b2 and isinstance(b1, A.AdapterBackend) and b1.name == "laya-mlx"
    assert b1.runtime.pid is None                                                    # resolving starts nothing
    assert isinstance(S.resolve_backend(None, cfg), S.NullBackend)
    with pytest.raises(ValueError, match="configured"):
        S.resolve_backend("laya-mlx")                                                # no cfg -> not resolvable
    with pytest.raises(ValueError):
        S.resolve_backend("not-defined", cfg)


@pytest.mark.parametrize("mutate,needle", [
    (lambda b: b["laya-mlx"].update(adapter="http"), "adapter must be one of"),
    (lambda b: b["laya-mlx"].pop("argv"), "argv must be a non-empty list"),
    (lambda b: b["laya-mlx"].update(argv=[]), "argv must be a non-empty list"),
    (lambda b: b["laya-mlx"].update(argv=["python", 3]), "argv must be a non-empty list"),
    (lambda b: b["laya-mlx"].update(timeout_seconds=0), "timeout_seconds must be a positive number"),
    (lambda b: b["laya-mlx"].update(timeout_seconds="fast"), "timeout_seconds must be a positive number"),
    (lambda b: b["laya-mlx"].update(cooldown_seconds=-1), "cooldown_seconds"),
    (lambda b: b.update(null=copy.deepcopy(b["laya-mlx"])), "collides with a built-in"),
])
def test_validate_rejects_bad_backend_definitions(cfg, mutate, needle):
    data = copy.deepcopy(cfg.data)
    mutate(data["systemone"]["backends"])
    assert any(needle in e for e in C.validate(C.Config(root=cfg.root, data=data))), needle


def test_validate_rejects_selecting_an_undefined_backend(cfg):
    data = copy.deepcopy(cfg.data)
    data["routing"]["systemone"] = {"backend": "ghost-model"}
    assert any("not a registered or configured backend" in e for e in C.validate(C.Config(root=cfg.root, data=data)))
    data["routing"]["systemone"] = {"backend": "laya-mlx"}
    errs = C.validate(C.Config(root=cfg.root, data=data))                            # defined, but not activatable
    assert any("benchmark-only adapter backend" in e for e in errs)                  # (see test_systemone_activation)


# ------------------------------------------------------------ router integration
CLS = {"type": "classification"}


def test_explicit_adapter_backend_is_used_and_narrows(cfg, tmp_path):
    c = _cfg_with_stub(cfg, tmp_path, "ok")                                          # stub picks the LAST option
    d = router.route(c, CLS)
    assert d.systemone["backend"] == "stub" and d.systemone["choice"] == "codex"
    assert d.systemone["confidence_kind"] == "raw" and d.systemone["escalate"] is False
    assert (d.provider, d.worker) == ("codex_subscription", "codex")


@pytest.mark.parametrize("mode,reason", [
    ("hang", "backend-timeout"), ("crash", "backend-unavailable"), ("garbage", "malformed-output"),
    ("huge", "malformed-output"), ("ineligible", "ineligible-choice"), ("missing", "unanswered-question"),
    ("error", "backend-error"), ("no_ready", "backend-unavailable")])
def test_any_adapter_failure_leaves_routing_exactly_as_before(cfg, tmp_path, mode, reason):
    base = router.route(cfg, CLS)
    d = router.route(_cfg_with_stub(cfg, tmp_path, mode), CLS)
    assert (d.stage, d.provider, d.worker, d.exit_state, d.fallbacks, d.failures) == (
        base.stage, base.provider, base.worker, base.exit_state, base.fallbacks, base.failures)
    assert d.systemone["escalate"] is True and d.systemone["reason"] == reason and d.systemone["choice"] is None
    assert [t for t in d.trace if "systemone" not in t] == [t for t in base.trace if "systemone" not in t]


def test_laya_unavailable_falls_back_without_failing_the_task(cfg):
    data = copy.deepcopy(cfg.data)
    data["systemone"]["backends"]["laya-mlx"]["argv"][0] = "/nonexistent/runtime/python"
    data["routing"]["systemone"] = {"backend": "laya-mlx"}
    c = C.Config(root=cfg.root, data=data)
    base = router.route(cfg, CLS)
    d = router.route(c, CLS)
    assert (d.provider, d.worker, d.exit_state) == (base.provider, base.worker, None)
    assert d.systemone["backend"] == "laya-mlx" and d.systemone["reason"] == "backend-unavailable"


def test_adapter_choice_is_still_bounded_by_policy(cfg, tmp_path):
    c = _cfg_with_stub(cfg, tmp_path, "ineligible")                                  # always answers "opencode"
    d = router.route(c, {**CLS, "eligible_workers": ["codex"]})
    assert d.systemone["reason"] == "ineligible-choice" and (d.provider, d.worker) == ("codex_subscription", "codex")
    ok = router.route(_cfg_with_stub(cfg, tmp_path, "ok"), {**CLS, "eligible_workers": ["claude_code"]})
    assert ok.worker == "claude_code"                                               # options were [claude_code] only


def test_high_risk_gate_still_precedes_the_adapter(cfg, tmp_path):
    c = _cfg_with_stub(cfg, tmp_path, "ok")
    d = router.route(c, {**CLS, "risk": "high"})
    assert d.exit_state == "human_handoff" and d.systemone is None
    assert A._CACHE == {} or all(b.runtime.pid is None for b in A._CACHE.values())   # nothing was even started


# ------------------------------------------------------------ default behaviour is untouched
def test_default_config_never_starts_a_process_or_changes_routing(cfg):
    A.close_all()
    plain = router.route(cfg, CLS, systemone_backend="null")
    d = router.route(cfg, CLS)
    assert d.to_dict() == plain.to_dict() and d.systemone["backend"] == "null" and d.systemone["reason"] == "no-backend"
    assert A._CACHE == {}                                                           # the adapter was never touched
    assert [t for t in d.trace if "systemone" not in t] == [
        "fastgate: skip — no usable model (candidates only)", "local_primary: skip — no usable model (candidates only)",
        "local_fallback: skip — no usable model (candidates only)", "C4: selected claude_subscription via claude_code"]


def test_laya_is_not_a_production_default_anywhere(cfg):
    assert cfg.routing["systemone"]["backend"] == "null"
    assert cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.models["models"]["laya-mlx"]["status"] in ("candidate", "available", "measured")
    assert os.path.exists(os.path.join(cfg.root, "agentos", "systemone_workers", "laya_worker.py"))
