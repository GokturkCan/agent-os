"""R3.2B: Laya-MLX smoke tests against the REAL local runtime (skipped where it is not installed).

The runtime lives in the git-ignored state/runtime/laya-mlx (see audit/laya-mlx-r3.2-2026-10-14.md for
the exact install). These tests are local and offline: the worker runs with a scrubbed environment and
loads pinned weights from disk. Laya is selected explicitly; it is never the default."""
import copy
from pathlib import Path

import pytest

from agentos import config as C
from agentos import router
from agentos import systemone as S
from agentos import systemone_adapter as A
from agentos import systemone_bench as B

ROOT = C.REPO_ROOT / "state" / "runtime" / "laya-mlx"
INSTALLED = (ROOT / "venv" / "bin" / "python").exists() and (
    ROOT / "models" / "laya-multilingual-mlx" / "model.safetensors").exists()
needs_laya = pytest.mark.skipif(not INSTALLED, reason="Laya-MLX runtime not installed (state/runtime/laya-mlx)")
CLS = {"type": "classification"}


@pytest.fixture(scope="module")
def laya():
    cfg = C.load()
    backend = A.backend_for("laya-mlx", cfg)
    yield backend
    A.close_all()


def _cfg_select(cfg, **overrides):
    data = copy.deepcopy(cfg.data)
    data["systemone"]["backends"]["laya-mlx"].update(overrides)
    data["routing"]["systemone"] = {"backend": "laya-mlx"}
    data["systemone"]["activation"]["production_backends"] = ["laya-mlx"]   # test-local copy of the protected allowlist
    return C.Config(root=cfg.root, data=data)


def _req(options=("claude_code", "codex"), **kw):
    return S.SystemOneRequest(task_type="classification", eligible_options=tuple(options), **kw,
                              questions=(S.Question("worker", "choose", "Which eligible worker should serve this task?"),),
                              state={"task_class": "classification", "stage": "fastgate"})


@needs_laya
def test_laya_backend_starts_and_reports_its_runtime(laya):
    resp = laya.decide(_req())
    assert not resp.escalate and resp.backend == "laya-mlx"
    rt = laya.runtime
    assert rt.pid is not None and rt.startup_seconds is not None and rt.startup_seconds < 30
    assert rt.info["laya_mlx"] == "0.4.0" and rt.info["mlx"] and "gpu" in rt.info["device"].lower()


@needs_laya
def test_one_choose_request_parses_into_a_typed_response(laya):
    resp = laya.decide(_req())
    assert isinstance(resp, S.SystemOneResponse) and resp.reason_code == "backend-choice"
    a = resp.answer("worker")
    assert a.choice in ("claude_code", "codex") and a.reason_code == "backend-choice"
    assert a.confidence.kind == "raw" and 0.0 <= a.confidence.value <= 1.0 and a.confidence.calibration_id is None
    via_contract = S.system_one(_req(), laya)
    assert not via_contract.escalate and via_contract.answer("worker").choice == a.choice


@needs_laya
def test_laya_confidence_is_raw_and_never_accepted_as_calibrated(laya):
    conf = laya.decide(_req()).answer("worker").confidence
    assert S.ConfidencePolicy(0.0, "any-calibrator").accepts(conf) == (False, "uncalibrated-confidence")


@needs_laya
def test_only_policy_eligible_options_are_ever_returned(laya):
    seen = 0
    for r in B.workload(40, seed=99):
        resp = laya.decide(r)
        assert not resp.escalate, resp.reason_code
        assert resp.answer("worker").choice in r.eligible_options            # never outside the offered set
        seen += 1
    assert seen == 40
    only = laya.decide(_req(options=("codex",)))
    assert only.answer("worker").choice == "codex"                            # a single option can only be that one


@needs_laya
def test_answers_are_deterministic(laya):
    answers = {laya.decide(_req()).answer("worker").choice for _ in range(5)}
    assert len(answers) == 1


@needs_laya
def test_worker_memory_stays_inside_the_model_budget(laya, cfg):
    laya.decide(_req())
    budget_kib = cfg.resources["nodes"]["mac"]["ram_budget_gb_for_models"] * 1024 * 1024
    assert 0 < laya.runtime.rss_kib() < budget_kib


@needs_laya
def test_router_with_laya_selected_routes_normally_and_is_narrowed_by_it(cfg):
    c = _cfg_select(cfg)
    d = router.route(c, CLS)
    s = d.systemone
    assert (d.stage, d.exit_state) == ("cloud", None) and s["backend"] == "laya-mlx" and s["escalate"] is False
    assert s["confidence_kind"] == "raw" and d.worker == s["choice"]
    A.close_all()


@needs_laya
def test_laya_cannot_widen_capability_eligibility(cfg):
    c = _cfg_select(cfg)
    d = router.route(c, {**CLS, "eligible_workers": ["codex"]})
    assert d.systemone["choice"] == "codex" and (d.provider, d.worker) == ("codex_subscription", "codex")
    A.close_all()


@needs_laya
def test_high_risk_gate_still_precedes_laya(cfg):
    c = _cfg_select(cfg)
    d = router.route(c, {**CLS, "risk": "high"})
    assert d.exit_state == "human_handoff" and d.systemone is None
    A.close_all()


@needs_laya
def test_timeout_with_the_real_model_falls_back_and_kills_the_worker(cfg):
    c = _cfg_select(cfg, timeout_seconds=0.001, cooldown_seconds=0)           # far below any real decision time
    base = router.route(cfg, CLS)
    d = router.route(c, CLS)
    assert d.systemone["reason"] == "backend-timeout" and d.systemone["escalate"] is True
    assert (d.provider, d.worker, d.exit_state) == (base.provider, base.worker, None)
    assert A.backend_for("laya-mlx", c).runtime.pid is None                   # killed on expiry
    A.close_all()


@needs_laya
def test_real_worker_with_an_unloadable_model_escalates_not_fails(cfg):
    argv = list(cfg.systemone["backends"]["laya-mlx"]["argv"])
    argv[argv.index("--model") + 1] = "{runtime}/models/does-not-exist"
    c = _cfg_select(cfg, argv=argv, cooldown_seconds=0)
    base = router.route(cfg, CLS)
    d = router.route(c, CLS)                                                  # worker script exits while loading
    assert d.systemone["reason"] == "backend-unavailable" and (d.worker, d.exit_state) == (base.worker, None)
    A.close_all()


@needs_laya
def test_laya_is_explicit_only_and_default_routing_is_unchanged(cfg):
    A.close_all()
    assert cfg.routing["systemone"]["backend"] == "null"
    d = router.route(cfg, CLS)
    assert d.systemone["backend"] == "null" and A._CACHE == {}                # default never touches the adapter
