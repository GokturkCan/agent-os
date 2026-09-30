"""Hermes -> agentos integration.

Pre-approval tests use Hermes' own code against a throwaway HERMES_HOME and a
stand-in worker; they never read secrets or write ~/.hermes. Tests marked
`hermes_wired` run only after the user applies the approved config change.
"""
import os
import subprocess
from pathlib import Path

import pytest

from agentos import hermes_bridge as hb
from agentos import telemetry, worktree
from agentos.config import REPO_ROOT
from agentos.dispatch import WORKER_CONTEXT_ENV, dispatch
from agentos.taskstate import TaskStore

needs_hermes = pytest.mark.skipif(not hb.available(), reason="Hermes not installed")
hermes_wired = pytest.mark.skipif(not hb.available() or not hb.is_wired(),
                                  reason="awaiting approved ~/.hermes/config.yaml change")
FIXED = "def add(a, b):\n    return a + b\n"


# ------------------------------------------------ Hermes discovers agentos
@needs_hermes
def test_hermes_discovers_agentos_skills_with_proposed_key():
    r = hb.probe()
    ok, detail = hb.probe_ok(r)
    assert ok, detail
    assert str(REPO_ROOT / "skills") in r["external_dirs"]
    for n in hb.AGENT_OS_SKILLS:
        assert r["skills"][n]["guard_verdict"] == "safe"
        assert not [f for f in r["skills"][n]["lint"] if f["severity"] == "error"]


@needs_hermes
def test_without_the_key_hermes_does_not_see_agentos():
    r = hb.probe({"skills": {}, "memory": {"memory_enabled": False}})
    assert not set(hb.AGENT_OS_SKILLS) & set(r["listed"])   # the key is what wires it


@needs_hermes
def test_proposed_disable_list_blocks_direct_worker_skills():
    seeded = tuple(n for n in hb.DIRECT_WORKER_SKILLS
                   if list((hb.HERMES_HOME / "skills").glob(f"*/{n}/SKILL.md")))
    if not seeded:
        pytest.skip("no bundled direct-worker skills installed")
    before = hb.probe(seed_skills=seeded)
    assert all(before["seeded"].values())                     # today: Hermes can load them
    after = hb.probe(hb.sandbox_config({"disabled": list(hb.DIRECT_WORKER_SKILLS)}), seed_skills=seeded)
    assert not any(after["seeded"].values())                  # proposed: they no longer load
    assert hb.probe_ok(after)[0]                              # agentos skills still fine


@needs_hermes
def test_probe_never_touches_live_hermes_home():
    cfg = hb.HERMES_HOME / "config.yaml"
    before = (cfg.stat().st_mtime_ns, cfg.read_bytes())
    hb.probe()
    assert (cfg.stat().st_mtime_ns, cfg.read_bytes()) == before


def test_wiring_and_bypass_detection_logic(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, "HERMES_HOME", tmp_path)
    for n in ("claude-code", "codex"):
        d = tmp_path / "skills" / "autonomous-ai-agents" / n
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: x\n---\n")
    assert not hb.is_wired({"skills": {"creation_nudge_interval": 15}})
    assert hb.is_wired({"skills": {"external_dirs": ["~/agent-stack/skills"]}})
    assert hb.direct_worker_skills_enabled({}) == ["claude-code", "codex"]
    assert hb.direct_worker_skills_enabled({"skills": {"disabled": ["claude-code", "codex"]}}) == []


# ------------------------------------------------------- entry point
def test_wrapper_runs_from_any_directory(tmp_path):
    out = subprocess.run([str(REPO_ROOT / "bin" / "agentos"), "route", "coding"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout
    assert '"worker": "claude_code"' in out


# ------------------------------------------------------------ dispatch
def _fixing_runner(seen):
    def run(launch, **kw):
        seen.append(launch)
        assert launch["env"][WORKER_CONTEXT_ENV]
        (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
        return {"returncode": 0, "latency_ms": 1.0}
    return run


def _noop_runner(launch, **kw):
    return {"returncode": 0, "latency_ms": 1.0}


def _dispatch(cfg, repo, tmp_path, runner, task_id="fix-add", **kw):
    return dispatch(cfg, task_id=task_id, task_type="coding", repo=repo, prompt="fix add()",
                    verify="python -m pytest -q -p no:cacheprovider", runner=runner,
                    worktree_root=tmp_path / "wts", **kw)


def test_dry_run_has_no_side_effects(cfg, fixture_repo, tmp_path):
    res = _dispatch(cfg, fixture_repo, tmp_path, runner=None, dry_run=True)
    assert res["status"] == "dry_run" and res["worker"] == "claude_code"
    assert "--strict-mcp-config" in res["launch_argv"]
    assert not (tmp_path / "wts").exists() and TaskStore(cfg).list() == []


def test_dispatch_success_commits_on_task_branch_only(cfg, fixture_repo, tmp_path):
    seen = []
    res = _dispatch(cfg, fixture_repo, tmp_path, _fixing_runner(seen))
    assert (res["status"], res["exit_state"]) == ("done", "success"), res
    assert res["verify"]["passed"] and res["commit"]
    wt = Path(res["worktree"])
    assert worktree.holder(wt) is None                       # lease released
    assert worktree.git(fixture_repo, "rev-parse", f"agentos/{res['task_id']}") == res["commit"]
    assert "a - b" in (fixture_repo / "calc.py").read_text()  # main checkout untouched
    assert worktree.git(fixture_repo, "branch", "--show-current") == "main"
    st = TaskStore(cfg).get("fix-add").state
    assert st["exit_state"] == "success" and st["plan_accepted"]["by"] == "hermes"
    assert telemetry.read_all()[-1]["exit_state"] == "success"
    assert seen[0]["cwd"] == str(wt.resolve())


def test_failed_verification_is_retryable_then_resumes_same_task(cfg, fixture_repo, tmp_path):
    first = _dispatch(cfg, fixture_repo, tmp_path, _noop_runner)
    assert (first["status"], first["exit_state"]) == ("retryable", None)
    seen = []
    second = _dispatch(cfg, fixture_repo, tmp_path, _fixing_runner(seen))
    assert second["status"] == "done" and second["worktree"] == first["worktree"]
    assert "# Resume brief — fix-add" in seen[0]["argv"][2]  # worker got file-backed state
    assert TaskStore(cfg).get("fix-add").state["attempts"] == 1


def test_budget_stops_retry_loop(cfg, fixture_repo, tmp_path):
    results = [_dispatch(cfg, fixture_repo, tmp_path, _noop_runner) for _ in range(4)]
    assert [r["status"] for r in results[:3]] == ["retryable", "retryable", "stopped"]
    assert results[2]["exit_state"] in ("budget_exhausted", "no_progress")
    assert results[3]["status"] == "closed"                    # no further work after the stop


def test_nested_dispatch_from_worker_is_refused(cfg, fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setenv(WORKER_CONTEXT_ENV, "outer-task")
    res = _dispatch(cfg, fixture_repo, tmp_path, _fixing_runner([]))
    assert (res["status"], res["exit_state"]) == ("refused", "unsafe")
    assert not (tmp_path / "wts").exists()


def test_high_risk_needs_human_before_any_side_effect(cfg, fixture_repo, tmp_path):
    res = _dispatch(cfg, fixture_repo, tmp_path, _fixing_runner([]), markers=("credential_change",))
    assert (res["status"], res["exit_state"]) == ("not_dispatched", "human_handoff")
    assert not (tmp_path / "wts").exists() and TaskStore(cfg).list() == []


def test_all_providers_down_blocks_dispatch(cfg, fixture_repo, tmp_path):
    res = _dispatch(cfg, fixture_repo, tmp_path, _fixing_runner([]),
                    health={"providers": {"claude_subscription": False, "codex_subscription": False}})
    assert res["exit_state"] == "blocked" and not (tmp_path / "wts").exists()


def test_provider_outage_dispatches_to_fallback_worker(cfg, fixture_repo, tmp_path):
    seen = []
    res = _dispatch(cfg, fixture_repo, tmp_path, _fixing_runner(seen),
                    health={"providers": {"claude_subscription": False}})
    assert res["worker"] == "codex" and seen[0]["argv"][:2] == ["codex", "exec"]
    assert "workspace-write" in seen[0]["argv"]


# ------------------------------------------------ single orchestrator
def test_agentos_never_invokes_hermes_or_merges():
    src = "\n".join(p.read_text() for p in (REPO_ROOT / "agentos").glob("*.py"))
    for forbidden in ('["hermes"', "'hermes',", '"merge"', '"push"'):
        assert forbidden not in src, forbidden


def test_hermes_is_not_a_selectable_worker(cfg):
    assert cfg.workers["workers"]["hermes_delegation"]["selectable"] is False
    for tc in cfg.routing["task_classes"].values():
        assert "hermes_delegation" not in tc.get("workers", [])


# --------------------------------------------------------------- live
@pytest.mark.live
@pytest.mark.skipif(os.environ.get("AGENTOS_LIVE") != "1", reason="set AGENTOS_LIVE=1")
def test_live_dispatch_cli_with_claude(fixture_repo, tmp_path):
    env = {**os.environ, "AGENTOS_WORKTREE_ROOT": str(tmp_path / "wts")}
    r = subprocess.run([str(REPO_ROOT / "bin" / "agentos"), "dispatch", "--task-id", "live-fix",
                        "--type", "coding", "--repo", str(fixture_repo), "--max-turns", "8",
                        "--prompt", "calc.add has a bug; fix calc.py only. Do not run git.",
                        "--verify", "python -m pytest -q -p no:cacheprovider"],
                       cwd=tmp_path, capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"status": "done"' in r.stdout


# ------------------------------------------- after approved config change
@hermes_wired
def test_live_hermes_config_loads_agentos_skills():
    cfg = hb.live_config()
    assert hb.is_wired(cfg)
    assert cfg["memory"]["memory_enabled"] is False           # unchanged invariant
    r = hb.probe({"skills": cfg["skills"], "memory": cfg["memory"]})   # live skills block, sandboxed home
    assert hb.probe_ok(r)[0]


@hermes_wired
def test_live_hermes_direct_worker_skills_disabled():
    assert hb.direct_worker_skills_enabled() == []


# ------------------------------------------ approved-change tooling itself
@needs_hermes
def test_wire_script_apply_verify_rollback_on_copy(tmp_path):
    """Exercise scripts/hermes-wire.py against a COPY of the live config (HOME=tmp)."""
    import sys
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    original = (hb.HERMES_HOME / "config.yaml").read_bytes()
    (home / ".hermes" / "config.yaml").write_bytes(original)
    run = lambda *a: subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "hermes-wire.py"), *a],
                                    env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
    assert run("apply").returncode == 2                          # no approval flag -> refused
    assert (home / ".hermes" / "config.yaml").read_bytes() == original
    assert run("apply", "--i-approve").returncode == 0
    import yaml
    new = yaml.safe_load((home / ".hermes" / "config.yaml").read_text())
    assert hb.is_wired(new) and new["skills"]["disabled"] == list(hb.DIRECT_WORKER_SKILLS)
    assert hb.probe_ok(hb.probe({"skills": new["skills"], "memory": new["memory"]}))[0]
    assert run("rollback").returncode == 0
    assert (home / ".hermes" / "config.yaml").read_bytes() == original   # byte-identical restore
