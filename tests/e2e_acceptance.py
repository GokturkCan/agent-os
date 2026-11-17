"""Four mandatory end-to-end acceptance scenarios (fixture vaults only)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentos.config import load
from agentos.knowledge import GateError
from agentos.project_continuity import project_status
from agentos.recall import recall
from agentos.taskstate import TaskStore

pytest_plugins = ["test_knowledge_lifecycle"]


def test_e2e1_knowledge_capture_recall_chain(world):
    """TEST 1 — capture proposal and recall against the fixture vault (no live apply)."""
    life, root, repo, _ = world
    p = life.capture(
        project="orbit",
        kind="research_question",
        summary="Evaluate Hohmann transfer windows for Q1 launches.",
        evidence=[{"kind": "user_statement", "locator": "hermes:acceptance-fixture"}],
        authorized=True,
    )
    assert p["state"] == "DRAFT"
    ctx = life.context("orbit", "Q1 launch windows", budget=8000, worker="claude_code", profile="coder")
    assert ctx["project"]["id"] == "orbit"
    cfg = load()
    hits = recall(cfg, "Orbit Planner scheduling", top=5, vault=root)
    assert hits["status"] in ("ok", "no_results")
    if hits["status"] == "ok":
        assert any("Orbit" in (h.get("path") or "") for h in hits["results"])


def test_e2e2_no_duplicate_project_entity(world):
    """TEST 2 — second capture attaches to the same project identity."""
    life, *_ = world
    before = len(life.projects.list())
    life.capture(
        project="orbit",
        kind="decision",
        summary="Use weekly scheduling cadence.",
        evidence=[{"kind": "user_statement", "locator": "acceptance-test"}],
        authorized=True,
    )
    life.capture(
        project="orbit",
        kind="decision",
        summary="Prefer ground-station polling over push when uncertain.",
        evidence=[{"kind": "user_statement", "locator": "acceptance-test-2"}],
        authorized=True,
    )
    assert len(life.projects.list()) == before


def _ensure_git_repo(repo: Path) -> None:
    if (repo / ".git").exists():
        return
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "accept@fixture.local"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Acceptance"], check=True)
    readme = repo / "README.md"
    if not readme.exists():
        readme.write_text("# Fixture repo\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)


def test_e2e3_stale_worktree_continuity(world, tmp_path):
    """TEST 3 — continuity survives stale checkout metadata."""
    life, _, repo, _ = world
    _ensure_git_repo(repo)
    cfg = load()
    bogus = tmp_path / "missing-worktree"
    TaskStore(cfg).create("ghost", {"goal": str(repo), "acceptance": ["continuity check"]}).claim(
        "codex", checkout=str(bogus)
    )
    st = project_status(cfg, life, "orbit", repo)
    assert st["project"]["id"] == "orbit"
    assert st["stale_worktrees"] and st["stale_worktrees"][0]["task_id"] == "ghost"


def test_e2e4_protected_gate_blocks_unapproved_apply(world):
    """TEST 4 — apply without a valid approval record must fail closed."""
    life, *_ = world
    p = life.capture(
        project="orbit",
        kind="idea",
        summary="Fixture-only idea for gate test",
        evidence=[{"kind": "user_statement", "locator": "acceptance-gate"}],
        authorized=True,
    )
    life.ready(p["id"])
    with pytest.raises(GateError, match="no approval record"):
        life.gate.apply(p["id"])