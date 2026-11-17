"""Workflow graph: parallel research, join, coding loop, repair, lesson."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from agentos.config import load
from agentos.knowledge import Vault, engine_cli
from agentos.knowledge_lifecycle import Lifecycle
from agentos.workflow_graph import WorkflowStore, repair_node, run_workflow, workflow_status
import test_knowledge_lifecycle as kfixture

FIXED = "def add(a, b):\n    return a + b\n"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def graph_world(tmp_path, monkeypatch):
    cfg = load()
    root = tmp_path / "vault"
    cli = engine_cli(cfg)
    plan = json.loads(subprocess.run([sys.executable, str(cli), "init", str(root)], capture_output=True, text=True, check=True).stdout)
    subprocess.run([sys.executable, str(cli), "init", str(root), "--apply", "--operation-id", plan["operation"]["operation_id"],
                    "--generated-at", plan["generated_at"], "--approved-plan-sha256", plan["approved_plan_sha256"]],
                   check=True, capture_output=True)
    kfixture.note(root, "wiki/projects/Orbit.md", "orbit", "Satellite planner.", entity_kind="project",
                  canonical_name="Orbit Planner", aliases=["Orbit"], repositories=[])
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a,b): return a-b\n")
    (repo / "test_calc.py").write_text("from calc import add\ndef test_add(): assert add(2,3)==5\n")
    env = {**dict(os.environ), "GIT_AUTHOR_NAME": "f", "GIT_AUTHOR_EMAIL": "f@l", "GIT_COMMITTER_NAME": "f", "GIT_COMMITTER_EMAIL": "f@l"}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(tmp_path / "state"))
    life = Lifecycle(cfg, vault=root, state=tmp_path / "state/knowledge/lifecycle", gate=Vault(cfg, root, tmp_path / "gate"))
    return cfg, life, repo, tmp_path


def test_parallel_research_join_implement_and_selective_repair(graph_world):
    cfg, life, repo, tmp = graph_world

    def fixing_runner(launch, **kw):
        (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
        return {"returncode": 0, "latency_ms": 1.0}

    spec = {
        "findings": {"research-a": "method A prefers low latency", "research-b": "method B prefers accuracy"},
        "nodes": [
            {"id": "research-a", "role": "research", "depends_on": []},
            {"id": "research-b", "role": "research", "depends_on": [], "inject_fail_once": True},
            {"id": "join", "role": "join", "depends_on": ["research-a", "research-b"]},
            {
                "id": "implement",
                "role": "coding",
                "depends_on": ["join"],
                "dispatch": {
                    "task_id": "wf-fix-add",
                    "repo": str(repo),
                    "verify": f"{sys.executable} -m pytest -q -p no:cacheprovider",
                    "prompt": "fix add()",
                },
            },
            {
                "id": "lesson",
                "role": "lesson",
                "depends_on": ["implement"],
                "lesson": {"project": "orbit", "from_task": "wf-fix-add", "kind": "lesson"},
            },
        ],
    }
    wf_id = "demo-graph"
    store = WorkflowStore(wf_id)
    store.spec_path().write_text(yaml.safe_dump(spec))

    start = {}
    from agentos import workflow_graph as wg

    orig = wg._run_research

    def timed_research(cfg, node, ctx):
        start[node["id"]] = time.monotonic()
        return orig(cfg, node, ctx)

    wg.DEFAULT_RUNNERS["research"] = timed_research

    first = run_workflow(cfg, wf_id, max_parallel=2, lifecycle=life, runner=fixing_runner,
                         worktree_root=tmp / "wts")
    assert first["status"] in ("failed", "blocked")
    assert workflow_status(wf_id)["nodes"]["research-a"]["status"] == "done"
    assert workflow_status(wf_id)["nodes"]["research-b"]["status"] == "failed"

    if start:
        assert abs(start.get("research-a", 0) - start.get("research-b", 0)) < 2.0

    repair_node(wf_id, "research-b")
    spec2 = yaml.safe_load(store.spec_path().read_text())
    for n in spec2["nodes"]:
        if n["id"] == "research-b":
            n.pop("inject_fail_once", None)
    store.spec_path().write_text(yaml.safe_dump(spec2))

    attempts_a = workflow_status(wf_id)["nodes"]["research-a"]["attempts"]
    second = run_workflow(cfg, wf_id, max_parallel=2, lifecycle=life, runner=fixing_runner,
                          worktree_root=tmp / "wts", resume=True)
    assert second["status"] == "done"
    st = workflow_status(wf_id)
    assert st["nodes"]["research-a"]["attempts"] == attempts_a
    assert all(st["nodes"][n]["status"] == "done" for n in st["nodes"])
    pid = second["state"]["nodes"]["lesson"]["artifact"]["proposal_id"]
    assert life.show(pid)["id"] == pid