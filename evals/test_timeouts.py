"""Real time-limit enforcement: worker + verifier deadlines kill the process
group, record a distinguishable timeout, keep retry/resume/lease semantics."""
import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from agentos import telemetry, worktree, workers
from agentos.dispatch import dispatch
from agentos.taskstate import TaskStore

FIXED = "def add(a, b):\n    return a + b\n"
PYTEST = f"{shlex.quote(sys.executable)} -m pytest -q -p no:cacheprovider"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _hanging_runner(seen=None):
    """Real worker process (via workers.run) that never finishes on its own."""
    def run(launch, **kw):
        launch = {**launch, "argv": [sys.executable, "-c", "import time; time.sleep(60)"]}
        if seen is not None:
            seen.append(kw["timeout"])
        return workers.run(launch, **kw)
    return run


def _fixing_runner(launch, **kw):
    (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
    return {"returncode": 0, "latency_ms": 1.0}


def _go(cfg, repo, tmp_path, runner, verify=PYTEST, **kw):
    return dispatch(cfg, task_id="tmo-task", task_type="coding", repo=repo, prompt="fix add()",
                    verify=verify, runner=runner, worktree_root=tmp_path / "wts", **kw)


# ------------------------------------------------------------ primitive
def test_run_bounded_kills_whole_process_group(tmp_path):
    pidfile = tmp_path / "child.pid"
    t0 = time.monotonic()
    r = workers.run_bounded(["sh", "-c", f"sleep 60 & echo $! > {pidfile}; wait"], cwd=tmp_path,
                            env=dict(os.environ), timeout=1, grace=2)
    assert r["timed_out"] and r["returncode"] is None
    assert time.monotonic() - t0 < 10
    pid = int(pidfile.read_text())
    time.sleep(0.2)
    assert not _alive(pid)                                   # grandchild did not survive


def test_run_bounded_normal_run_unchanged(tmp_path):
    r = workers.run_bounded(["sh", "-c", "echo hi; echo err >&2; exit 3"], cwd=tmp_path,
                            env=dict(os.environ), timeout=10)
    assert (r["returncode"], r["stdout"].strip(), r["stderr"].strip(), r["timed_out"]) == (3, "hi", "err", False)


def test_workers_run_timeout_is_distinct_and_cleans_files(tmp_path):
    f = tmp_path / "mcp.json"
    f.write_text("{}")
    res = workers.run({"argv": [sys.executable, "-c", "import time; time.sleep(60)"], "cwd": str(tmp_path),
                       "worker": "codex", "files": {"mcp": str(f)}}, task_id="tmo-prim", timeout=1)
    assert res["timed_out"] and res["returncode"] is None
    assert not f.exists()
    assert telemetry.read_all()[-1]["exit_state"] == "timeout"


# ------------------------------------------------------------- dispatch
def test_worker_timeout_is_recorded_and_retryable(cfg, fixture_repo, tmp_path):
    limits = []
    res = _go(cfg, fixture_repo, tmp_path, _hanging_runner(limits), timeout=1)
    assert (res["status"], res["exit_state"], res["timed_out"]) == ("retryable", None, True), res
    assert limits == [1] and res["verify"]["summary"].startswith("worker timeout")
    st = TaskStore(cfg).get("tmo-task").state
    assert st["attempts"] == 1 and st["exit_state"] is None
    assert st["timeouts"][0]["stage"] == "worker" and st["timeouts"][0]["limit"] == "per_call"
    assert st["elapsed_seconds"] > 0
    assert "timeout: worker" in (TaskStore(cfg).get("tmo-task").path / "findings.md").read_text()
    assert worktree.holder(Path(res["worktree"])) is None   # lease released
    assert "timeout" in telemetry.read_all()[-1]["notes"]


def test_resume_after_timeout_succeeds(cfg, fixture_repo, tmp_path):
    assert _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)["status"] == "retryable"
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    assert (res["status"], res["exit_state"], res["timed_out"]) == ("done", "success", False), res
    st = TaskStore(cfg).get("tmo-task").state
    assert st["exit_state"] == "success" and st["attempts"] == 1 and len(st["timeouts"]) == 1


def test_repeated_timeouts_exhaust_with_timeout_exit_state(cfg, fixture_repo, tmp_path):
    results = [_go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1) for _ in range(3)]
    assert [r["status"] for r in results] == ["retryable", "retryable", "stopped"]
    assert results[-1]["exit_state"] == "timeout"
    st = TaskStore(cfg).get("tmo-task").state
    assert st["exit_state"] == "timeout" and "timeout" in st["close_reason"] and len(st["timeouts"]) == 3
    assert worktree.holder(Path(results[-1]["worktree"])) is None
    assert _go(cfg, fixture_repo, tmp_path, _fixing_runner)["status"] == "closed"   # no more attempts


def test_verifier_timeout_cannot_run_forever(cfg, fixture_repo, tmp_path):
    hang = f"{sys.executable} -c 'import time; time.sleep(60)'"
    t0 = time.monotonic()
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner, verify=hang, verify_timeout=1)
    assert time.monotonic() - t0 < 20
    assert (res["status"], res["timed_out"]) == ("retryable", True), res
    assert res["verify"]["timed_out"] and "verification timeout" in res["verify"]["summary"]
    st = TaskStore(cfg).get("tmo-task").state
    assert st["timeouts"][0]["stage"] == "verify" and st["attempts"] == 1
    assert worktree.holder(Path(res["worktree"])) is None


def test_wall_clock_budget_caps_worker_and_blocks_new_attempts(cfg, fixture_repo, tmp_path):
    limits = []
    first = _go(cfg, fixture_repo, tmp_path, _hanging_runner(limits), timeout=1)
    assert first["status"] == "retryable"
    task = TaskStore(cfg).get("tmo-task")
    st = task.state
    st["budgets"]["wall_clock_minutes"] = 1                   # 60s total
    st["elapsed_seconds"] = 58.0                              # 2s left
    task._save(st)
    res = _go(cfg, fixture_repo, tmp_path, _hanging_runner(limits), timeout=1800)
    assert limits[-1] <= 2                                    # per-call limit clamped to remaining budget
    assert res["exit_state"] == "timeout" and res["status"] == "stopped", res
    assert TaskStore(cfg).get("tmo-task").state["timeouts"][-1]["limit"] == "wall_clock"
    assert worktree.holder(Path(res["worktree"])) is None


def test_exhausted_wall_clock_does_not_start_worker(cfg, fixture_repo, tmp_path):
    _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)
    task = TaskStore(cfg).get("tmo-task")
    st = task.state
    st["elapsed_seconds"] = st["budgets"]["wall_clock_minutes"] * 60
    task._save(st)
    called = []
    res = _go(cfg, fixture_repo, tmp_path, lambda *a, **k: called.append(1))
    assert not called and (res["status"], res["exit_state"]) == ("stopped", "timeout")
    assert worktree.holder(Path(res["worktree"])) is None


# ------------------------------------------------------------ regression
def test_non_timeout_success_unchanged(cfg, fixture_repo, tmp_path):
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner, timeout=30)
    assert (res["status"], res["exit_state"], res["timed_out"]) == ("done", "success", False)
    assert res["commit"] and res["verify"]["passed"]
    st = TaskStore(cfg).get("tmo-task").state
    assert not st.get("timeouts") and st["exit_state"] == "success"


def test_non_timeout_failure_still_budget_exhausted(cfg, fixture_repo, tmp_path):
    noop = lambda launch, **kw: {"returncode": 0, "latency_ms": 1.0}
    res = [_go(cfg, fixture_repo, tmp_path, noop) for _ in range(3)]
    assert res[-1]["exit_state"] == "budget_exhausted" and not res[-1]["timed_out"]
