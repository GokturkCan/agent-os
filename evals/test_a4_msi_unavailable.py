"""Acceptance 4 — MSI UNAVAILABLE (+ resource-scheduling family)."""
from agentos import health, router
from agentos.resources import ResourceScheduler, probe_node

DOWN = {"nodes": {"msi": False, "mac": True}}
UP = {"nodes": {"msi": True, "mac": True}}


def test_control_plane_healthy_without_msi(cfg, monkeypatch):
    monkeypatch.setenv("AGENTOS_NODE_MSI", "down")
    results = health.run_checks(cfg)
    msi = [r for r in results if r["check"] == "node.msi"][0]
    assert msi["status"] == "INFO" and "reachable=False" in msi["detail"]
    assert not [r for r in results if r["status"] == "FAIL"], results


def test_msi_probe_is_bounded_and_nonfatal(cfg, monkeypatch):
    monkeypatch.delenv("AGENTOS_NODE_MSI", raising=False)
    p = probe_node(cfg, "msi")                            # real probe: alias not configured today
    assert p["reachable"] in (True, False) and p["reason"]


def test_reasoning_falls_back_to_cloud_when_msi_down(cfg):
    d = router.route(cfg, {"type": "summarization"}, DOWN)
    assert d.stage == "cloud" and d.exit_state is None
    assert any("local_primary: skip" in t for t in d.trace)


def test_candidate_local_model_never_used_even_if_msi_up(cfg):
    d = router.route(cfg, {"type": "summarization"}, UP)
    assert d.stage == "cloud"                             # qwen is a candidate, not measured


def test_gpu_workload_blocks_cleanly_when_msi_down(cfg):
    d = router.route(cfg, {"type": "gpu_workload"}, DOWN)
    assert d.exit_state == "blocked"
    assert d.failures == [{"node": "msi", "reason": "unreachable"}]


def test_profile_transition_refused_when_unreachable(cfg):
    plan = ResourceScheduler(cfg).plan_transition("ROBOTICS", node_reachable=False)
    assert not plan["ok"] and plan["exit_state"] == "blocked"


def test_profile_transition_requires_every_step_in_order(cfg):
    s = ResourceScheduler(cfg)
    plan = s.plan_transition("ML_TRAIN", node_reachable=True)
    assert plan["ok"] and plan["steps"][0] == "drain_inflight_llm_requests"
    assert not s.apply_step_log(plan, ["unload_llm_runtime"])["ok"]           # skipped drain
    assert not s.apply_step_log(plan, plan["steps"][:3])["ok"]                # incomplete
    assert s.apply_step_log(plan, plan["steps"])["ok"]
    assert s.state()["msi"]["profile"] == "LLM_INFERENCE"                     # restored default


def test_msi_is_not_boot_critical(cfg):
    assert cfg.resources["nodes"]["msi"]["boot_critical"] is False
