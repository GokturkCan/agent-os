"""Acceptance 5 — PROVIDER FAILURE (+ routing / fallback-recovery families)."""
from agentos import router, telemetry


def _record(d):
    return telemetry.record(task_type=d.task_type, route=d.stage, provider=d.provider,
                            worker=d.worker, exit_state=d.exit_state,
                            fallbacks=d.fallbacks, failures=d.failures)


def test_primary_provider_down_falls_back_to_next_valid(cfg):
    d = router.route(cfg, {"type": "coding"}, {"providers": {"claude_subscription": False}})
    assert (d.provider, d.worker) == ("codex_subscription", "codex")
    assert {"provider": "claude_subscription", "reason": "unhealthy at runtime"} in d.failures
    rec = _record(d)
    assert rec["failures"][0]["provider"] == "claude_subscription"      # visible in telemetry
    assert telemetry.read_all()[-1]["fallbacks"] == ["claude_subscription"]


def test_all_providers_down_is_blocked_not_retried(cfg):
    d = router.route(cfg, {"type": "coding"},
                     {"providers": {"claude_subscription": False, "codex_subscription": False}})
    assert d.exit_state == "blocked" and d.provider is None
    assert len(d.failures) == 2
    assert _record(d)["exit_state"] == "blocked"


def test_disabled_provider_never_selected(cfg):
    # kimi-k3 / deepseek_direct / openrouter are not in any chain; nvidia only for background
    d = router.route(cfg, {"type": "background_coding_escalation"})
    assert d.provider == "nvidia_nim" and d.worker == "deepseek_harness"
    d = router.route(cfg, {"type": "background_coding_escalation"}, {"providers": {"nvidia_nim": False}})
    assert d.exit_state == "blocked"                       # no silent escalation to an unapproved provider


def test_worker_outage_falls_back(cfg):
    d = router.route(cfg, {"type": "review"}, {"workers": {"claude_code": False}})
    assert d.worker == "codex"


def test_high_risk_requires_human_regardless(cfg):
    d = router.route(cfg, {"type": "coding", "markers": ["credential_change"]})
    assert d.exit_state == "human_handoff" and d.requires_human_approval
    d = router.route(cfg, {"type": "coding", "risk": "high", "human_approval_ref": "human:ok"})
    assert d.exit_state is None and d.requires_human_approval


def test_deterministic_events_use_no_model(cfg):
    d = router.route(cfg, {"type": "test_result"})
    assert d.handler == "deterministic" and d.provider is None


def test_unknown_task_class_blocks(cfg):
    assert router.route(cfg, {"type": "teleport"}).exit_state == "blocked"


def test_fastgate_skipped_while_candidate(cfg):
    d = router.route(cfg, {"type": "classification"})
    assert any("fastgate: skip" in t for t in d.trace) and d.stage == "cloud"
