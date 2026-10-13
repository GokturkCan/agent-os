"""Acceptance 6 — LONG-TASK RESUME. Context loss is simulated by a fresh
process that only has the state directory."""
import os
import subprocess
import sys

import pytest

from agentos.taskstate import TaskError, TaskStore


def _seed(cfg):
    t = TaskStore(cfg).create("long-refactor", {
        "goal": "Refactor parser into modules", "acceptance": ["all tests pass", "no API change"],
        "task_class": "coding", "verification": "pytest -q"})
    t.accept_plan("1. extract lexer\n2. extract ast\n3. rewire imports", accepted_by="operator")
    t.claim("claude_code", checkout="/tmp/wt-long-refactor")
    t.iterate("5 failing", "extracted lexer")
    t.record_files(["parser/lexer.py", "parser/__init__.py"])
    t.fail_hypothesis("circular import from ast->lexer", "ImportError at test collection")
    t.record_test("pytest -q", False, "3 failed, 12 passed")
    t.iterate("3 failing", "fixed import cycle")
    t.checkpoint("after-lexer")
    return t


def test_resume_from_files_in_fresh_process(cfg):
    t = _seed(cfg)
    env = {**os.environ}
    out = subprocess.run([sys.executable, "-m", "agentos.cli", "task", "resume", t.id],
                         capture_output=True, text=True, env=env, check=True).stdout
    for needle in ("Refactor parser into modules", "extract lexer", "parser/lexer.py",
                   "circular import", "3 failed, 12 passed", "after-lexer", "iteration 2/30"):
        assert needle in out, needle


def test_handoff_between_workers(cfg):
    t = _seed(cfg)
    with pytest.raises(TaskError):
        t.claim("codex")                                  # owned: no concurrent mutation
    t.handoff("codex", "context budget exhausted")
    assert (t.path / "handoff.md").read_text().startswith("# Resume brief")
    t.claim("codex")
    assert t.state["owner"] == "codex" and t.state["handoffs"][0]["from"] == "claude_code"


def test_no_progress_forces_exit(cfg):
    t = TaskStore(cfg).create("spinner", {"goal": "g", "acceptance": ["a"]})
    results = [t.iterate("4 failing") for _ in range(4)]
    assert results[-1] == "no_progress"
    assert t.state["exit_state"] == "no_progress"
    with pytest.raises(TaskError):
        t.iterate("4 failing")                            # closed tasks cannot spin


def test_iteration_and_attempt_budgets_bound_retries(cfg):
    t = TaskStore(cfg).create("bounded", {"goal": "g", "acceptance": ["a"],
                                          "budgets": {"max_iterations": 3}})
    assert [t.iterate(i) for i in range(3)][-1] == "budget_exhausted"
    t2 = TaskStore(cfg).create("retries", {"goal": "g", "acceptance": ["a"]})
    assert [t2.attempt_failed("x") for _ in range(3)] == [None, None, "budget_exhausted"]


def test_contract_rejects_unknown_fields_and_bad_exit_states(cfg):
    with pytest.raises(TaskError):
        TaskStore(cfg).create("bad", {"goal": "g", "acceptance": ["a"], "vibes": 1})
    t = TaskStore(cfg).create("ok-task", {"goal": "g", "acceptance": ["a"]})
    with pytest.raises(TaskError):
        t.close("done-ish")
