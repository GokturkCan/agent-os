"""Live authorized worker: execute → verify fail → repair → pass (skips without harness)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from agentos.config import load
from agentos.dispatch import dispatch
from agentos.taskstate import TaskStore

pytestmark = pytest.mark.integration


def _pick_worker() -> str | None:
    if shutil.which("codex"):
        return "codex"
    if shutil.which("claude"):
        return "claude_code"
    return None


@pytest.fixture
def worker_repo(tmp_path):
    repo = tmp_path / "worker-fixture"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (repo / "test_calc.py").write_text("from calc import add\ndef test_add():\n    assert add(2, 3) == 5\n")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "agentos",
        "GIT_AUTHOR_EMAIL": "agentos@test",
        "GIT_COMMITTER_NAME": "agentos",
        "GIT_COMMITTER_EMAIL": "agentos@test",
    }
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    return repo


@pytest.fixture
def worker_state(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(root))
    monkeypatch.setenv("AGENTOS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    monkeypatch.setenv("AGENTOS_RESOURCE_STATE", str(tmp_path / "resources.json"))
    monkeypatch.setenv("AGENTOS_WORKTREE_ROOT", str(tmp_path / "worktrees"))


def test_authorized_worker_fail_then_repair_verify(worker_repo, worker_state):
    worker = _pick_worker()
    if not worker:
        pytest.skip("no authorized worker binary (codex or claude) on PATH")
    cfg = load()
    health = {}
    task_id = f"live-worker-{uuid.uuid4().hex[:8]}"
    verify = f"{sys.executable} -m pytest -q -p no:cacheprovider && test -f WORKER_PHASE1"
    r1 = dispatch(
        cfg,
        task_id=task_id,
        task_type="coding",
        repo=worker_repo,
        prompt=(
            "Phase 1 only: create an empty file named WORKER_PHASE1 in the repo root. "
            "Do not change calc.py."
        ),
        verify=verify,
        health=health,
        max_turns=12,
        timeout=240,
        verify_timeout=120,
    )
    assert r1["worker"] in ("claude_code", "codex")
    assert r1["status"] in ("retryable", "stopped", "done")
    if r1["status"] == "done":
        pytest.skip("worker completed both phases in one attempt; repair loop not observable")
    assert r1.get("verify") and not r1["verify"].get("passed")

    verify2 = f"{sys.executable} -m pytest -q -p no:cacheprovider"
    r2 = dispatch(
        cfg,
        task_id=task_id,
        task_type="coding",
        repo=worker_repo,
        prompt="Phase 2: fix calc.add so pytest passes. Keep WORKER_PHASE1 if present.",
        verify=verify2,
        health=health,
        max_turns=12,
        timeout=240,
        verify_timeout=120,
    )
    assert r2["worker"] == r1["worker"]
    assert r2["status"] == "done" and r2["verify"]["passed"]
    st = TaskStore(cfg).get(task_id).state
    tests = st.get("tests") or []
    assert len(tests) >= 2 and not tests[0]["passed"] and tests[-1]["passed"]
    assert st["exit_state"] == "success"