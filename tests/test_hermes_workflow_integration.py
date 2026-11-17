"""NL workflow request + integrated fixture pipeline."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentos.config import load
from agentos.hermes_workflow import continue_workflow, execute_workflow_request, plan_workflow_request
from agentos.workflow_graph import WorkflowError, workflow_status
import test_knowledge_lifecycle as kf

pytest_plugins = ["test_knowledge_lifecycle"]

FIXED = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def pipeline_world(knowledge_world):
    life, root, repo, _ = knowledge_world
    (repo / "calc.py").write_text("def add(a,b): return a-b\n")
    (repo / "test_calc.py").write_text("from calc import add\ndef test_add(): assert add(2,3)==5\n")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "f",
        "GIT_AUTHOR_EMAIL": "f@l",
        "GIT_COMMITTER_NAME": "f",
        "GIT_COMMITTER_EMAIL": "f@l",
    }
    if not (repo / ".git").exists():
        for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-qm", "init"]):
            subprocess.run(cmd, cwd=repo, check=True, env=env)
    return load(), life, repo


SMOKE_TWO_APPROACHES = (
    "Research two approaches, compare them, implement a prototype, "
    "verify results and preserve lessons."
)


def test_smoke_two_approaches_plan_regression(pipeline_world):
    """CLI smoke input: dual research, distinct branch tasks, join both, scoped impl repo."""
    cfg, life, fixture_repo = pipeline_world
    plan = plan_workflow_request(
        cfg,
        text=SMOKE_TWO_APPROACHES,
        project_query="Orbit",
        repo=cfg.root,
        lifecycle=life,
    )
    assert plan["status"] == "planned" and plan["dual_research"] is True
    assert plan["planned_nodes"].count("research-a") == plan["planned_nodes"].count("research-b") == 1
    join = next(n for n in plan["spec"]["nodes"] if n["id"] == "join")
    assert join["depends_on"] == ["research-a", "research-b"]
    fa, fb = plan["spec"]["findings"]["research-a"], plan["spec"]["findings"]["research-b"]
    assert fa != fb and "[task]" in fa and "branch B" in fb
    assert "research-b" not in plan["spec"]["findings"] or fb != fa
    impl = next(n for n in plan["spec"]["nodes"] if n["id"] == "implement")
    assert Path(impl["dispatch"]["repo"]).resolve() == fixture_repo.resolve()
    assert "Scope:" in impl["dispatch"]["prompt"]
    assert Path(impl["dispatch"]["repo"]).resolve() != cfg.root.resolve()


def test_nl_plan_dual_research_nodes(pipeline_world):
    cfg, life, repo = pipeline_world
    text = "Run two independent research tasks, join, implement, and remember."
    plan = plan_workflow_request(cfg, text=text, project_query="Orbit", repo=repo, lifecycle=life)
    assert plan["schema"] == "agentos.hermes-workflow-plan.v1"
    assert plan["status"] == "planned" and plan["dual_research"] is True
    assert "research-a" in plan["planned_nodes"] and "research-b" in plan["planned_nodes"]


def test_integrated_nl_fixture_pipeline(pipeline_world, monkeypatch, tmp_path):
    cfg, life, repo = pipeline_world
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(life.state.parent.parent))

    def fixing_runner(launch, **kw):
        (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
        return {"returncode": 0, "latency_ms": 1.0}

    text = (
        "Run two independent research tasks on predictive mapping, combine results, "
        "implement a small fix in the repo, verify tests, and capture a lesson."
    )
    out = execute_workflow_request(
        cfg,
        text=text,
        project_query="Orbit",
        repo=repo,
        max_parallel=2,
        runner=fixing_runner,
        worktree_root=tmp_path / "wts",
        lifecycle=life,
    )
    assert out["schema"] == "agentos.hermes-workflow-execute.v1"
    assert out["status"] == "done"
    assert out["evidence"]["checkpoint_seq"] >= 1
    st = workflow_status(out["workflow_id"])
    assert all(v["status"] == "done" for v in st["nodes"].values())
    pid = out["execution"]["state"]["nodes"]["lesson"]["artifact"]["proposal_id"]
    assert life.show(pid)["id"] == pid

    cont = continue_workflow(cfg, workflow_id=out["workflow_id"], project_query="Orbit", lifecycle=life)
    assert cont["schema"] == "agentos.hermes-workflow-continue.v1"
    assert cont["status"] == "done"
    assert cont["continuity"]["schema"] == "agentos.where-stopped.v1"


def test_workflow_request_cli_entrypoint(pipeline_world, monkeypatch, tmp_path):
    cfg, life, repo = pipeline_world
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(life.state.parent.parent))

    def fixing_runner(launch, **kw):
        (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
        return {"returncode": 0, "latency_ms": 1.0}

    from agentos import workflow_cli
    from argparse import Namespace

    args = Namespace(
        workflow_action="request",
        text="Two research tasks then implement",
        project="Orbit",
        repo=str(repo),
        workflow_id=None,
        max_parallel=2,
        resume=False,
    )
    monkeypatch.setattr(
        "agentos.workflow_cli.execute_workflow_request",
        lambda *a, **k: execute_workflow_request(
            *a,
            **{
                **k,
                "runner": fixing_runner,
                "worktree_root": tmp_path / "cli-wt",
                "lifecycle": life,
            },
        ),
    )
    code = workflow_cli.run(cfg, args)
    assert code == 0