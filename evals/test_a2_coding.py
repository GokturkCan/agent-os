"""Acceptance 2 — CODING (+ worker-dispatch family).

fixture repo -> routed primary worker -> isolated worktree with a single-owner
lease -> explicit task state -> deterministic verification -> clean completion.

The code change itself is applied by a deterministic stand-in for the worker
so the suite is reproducible and free; `test_live_claude_worker` (opt-in,
AGENTOS_LIVE=1) runs the real Claude Code worker on the same fixture.
"""
import os
import subprocess
import sys

import pytest

from agentos import router, telemetry, worktree
from agentos.permissions import WorkerSession
from agentos.taskstate import TaskStore
from agentos.workers import build_launch, run

from .conftest import git_env


def pytest_cmd(cwd):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                       cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return r.returncode == 0, r.stdout.strip().splitlines()[-1]


def test_coding_task_end_to_end(cfg, fixture_repo, tmp_path):
    decision = router.route(cfg, {"type": "coding"})
    assert decision.worker == "claude_code" and decision.exit_state is None

    store = TaskStore(cfg)
    task = store.create("fix-calc-add", {
        "goal": "Make add() return the sum", "acceptance": ["pytest passes in fixture repo"],
        "task_class": "coding", "verification": "python -m pytest -q", "profile": "coder"})
    task.accept_plan("1. fix operator in calc.add\n2. run pytest", accepted_by="operator")

    wt = worktree.create(fixture_repo, task.id, tmp_path / "worktrees")
    worktree.acquire(wt, decision.worker, task.id)
    task.claim(decision.worker, checkout=str(wt))

    # a second coding agent cannot mutate the same checkout
    with pytest.raises(worktree.LeaseError):
        worktree.acquire(wt, "codex", task.id)

    launch = build_launch(cfg, WorkerSession.start(cfg, decision.worker), "fix add()", wt)
    assert launch["cwd"] == str(wt.resolve())

    ok, summary = pytest_cmd(wt)
    assert not ok
    task.record_test("pytest -q", ok, summary)
    task.iterate(progress_signal="2 failing", note="baseline")

    (wt / "calc.py").write_text("def add(a, b):\n    return a + b\n")   # worker stand-in
    task.record_files(["calc.py"])
    ok, summary = pytest_cmd(wt)
    task.record_test("pytest -q", ok, summary)
    assert ok, summary
    task.iterate(progress_signal="0 failing", note="fixed")

    subprocess.run(["git", "commit", "-qam", "fix add"], cwd=wt, check=True, env=git_env())
    assert worktree.is_clean(wt)
    worktree.release(wt, decision.worker)
    task.close("success", "pytest green")
    telemetry.record(task_id=task.id, task_type="coding", worker=decision.worker,
                     provider=decision.provider, exit_state="success", success=True,
                     artifacts=[worktree.git(wt, "rev-parse", "HEAD")])

    # main checkout untouched; result lives on the task branch only
    assert "a - b" in (fixture_repo / "calc.py").read_text()
    assert worktree.git(fixture_repo, "log", "--oneline", f"agentos/{task.id}", "-1").endswith("fix add")
    st = task.state
    assert st["exit_state"] == "success" and st["tests"][-1]["passed"] and st["owner"] is None
    worktree.remove(fixture_repo, wt)
    assert not wt.exists()
    assert telemetry.read_all()[-1]["exit_state"] == "success"


def test_worktree_refuses_removal_when_dirty_or_leased(fixture_repo, tmp_path):
    wt = worktree.create(fixture_repo, "dirty", tmp_path / "wts")
    worktree.acquire(wt, "codex", "dirty")
    with pytest.raises(worktree.LeaseError):
        worktree.remove(fixture_repo, wt)
    with pytest.raises(worktree.LeaseError):
        worktree.release(wt, "claude_code")              # only the holder may release
    worktree.release(wt, "codex")
    (wt / "calc.py").write_text("changed")
    with pytest.raises(worktree.LeaseError):
        worktree.remove(fixture_repo, wt)
    assert wt.exists()


def test_code_index_freshness_is_per_worktree(fixture_repo, tmp_path):
    """Derived code indexes (Serena/codebase-memory/repomix) must be treated as
    stale when HEAD or the working diff moves, and are never shared across
    worktrees."""
    a = worktree.create(fixture_repo, "idx-a", tmp_path / "wts")
    b = worktree.create(fixture_repo, "idx-b", tmp_path / "wts")
    sa = worktree.index_stamp(a)
    assert worktree.is_fresh(a, sa)
    assert not worktree.is_fresh(b, sa)                   # other worktree != same index
    (a / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    assert not worktree.is_fresh(a, sa)                   # dirty edit -> stale
    subprocess.run(["git", "commit", "-qam", "x"], cwd=a, check=True, env=git_env())
    assert not worktree.is_fresh(a, sa)                   # new HEAD -> stale
    assert worktree.is_fresh(a, worktree.index_stamp(a))


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("AGENTOS_LIVE") != "1", reason="set AGENTOS_LIVE=1")
def test_live_claude_worker(cfg, fixture_repo, tmp_path):
    wt = worktree.create(fixture_repo, "live", tmp_path / "wts")
    worktree.acquire(wt, "claude_code", "live")
    launch = build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"),
                          "calc.add has a bug; fix calc.py so `python -m pytest -q` passes. "
                          "Edit only calc.py. Do not run git.", wt, max_turns=8)
    res = run(launch, task_id="live", timeout=300)
    ok, summary = pytest_cmd(wt)
    assert res["returncode"] == 0, res["stderr"]
    assert ok, summary
    assert res["telemetry"]["latency_ms"] > 0
    changed = worktree.git(wt, "status", "--porcelain")
    assert changed.strip() == "M calc.py"                 # stayed inside its scope
