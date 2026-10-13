"""Regression family: config integrity and honest status claims."""
from pathlib import Path

import yaml

from agentos import config as C


def test_config_valid(cfg):
    assert C.validate(cfg) == []


def test_no_candidate_claimed_usable(cfg):
    for name, tier in cfg.models["tiers"].items():
        if tier.get("model"):
            assert cfg.models["models"][tier["model"]]["status"] in C.USABLE
    for name, p in cfg.providers["providers"].items():
        if p.get("locality") == "local":
            assert p["enabled"] is False, f"{name}: no local runtime has been measured"


def test_disabled_models_not_in_any_route(cfg):
    disabled = {n for n, m in cfg.models["models"].items() if m["status"] == "disabled"}
    text = (C.REPO_ROOT / "config" / "routing.yaml").read_text()
    assert not any(d in text for d in disabled)


def test_hermes_memory_stays_disabled():
    p = Path.home() / ".hermes" / "config.yaml"
    if not p.exists():
        return
    mem = (yaml.safe_load(p.read_text()) or {}).get("memory", {})
    assert mem.get("memory_enabled") is False and mem.get("user_profile_enabled") is False


def test_worker_exposure_never_includes_account_connectors(cfg):
    for prof, names in cfg.mcp["exposure"].items():
        assert "claude_ai_connectors" not in names and "notion" not in names, prof


def test_remote_presence_is_not_a_health_warning():
    from agentos import health
    assert health.remote_state("origin")[0] == "PASS"
    assert health.remote_state("origin\nbackup")[0] == "PASS"
    assert health.remote_state("")[0] == "INFO"                 # absence is informational, not a failure
    detail = health.remote_state("origin")[1]
    assert "never push" in detail and "git@" not in detail and "http" not in detail   # names only


def test_health_reports_remote_without_warning(cfg):
    from agentos import health
    rows = {r["check"]: r for r in health.run_checks(cfg)}
    assert "repo.no_remote" not in rows and rows["repo.remote"]["status"] in ("PASS", "INFO")
