"""Bounded dependency-aware workflow execution (Agent OS operational layer).

Not a second orchestrator: persists node state under state/workflows/ and reuses
dispatch(), taskstate, and knowledge contracts for worker and lesson nodes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .config import Config, REPO_ROOT
from .dispatch import dispatch
from .hermes_knowledge import capture_remember
from .knowledge_lifecycle import Lifecycle
from .taskstate import TaskStore, state_root

SCHEMA = "agentos.workflow.v1"
NodeRunner = Callable[[Config, dict, dict], dict]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def workflows_root() -> Path:
    return Path(os.environ.get("AGENTOS_STATE_DIR", REPO_ROOT / "state")) / "workflows"


class WorkflowError(Exception):
    pass


class WorkflowStore:
    def __init__(self, workflow_id: str):
        if not workflow_id.replace("-", "").replace("_", "").isalnum():
            raise WorkflowError("workflow_id must be alphanumeric slug")
        self.id = workflow_id
        self.path = workflows_root() / workflow_id
        self.path.mkdir(parents=True, exist_ok=True)

    def spec_path(self) -> Path:
        return self.path / "workflow.yaml"

    def state_path(self) -> Path:
        return self.path / "state.json"

    def artifact_dir(self) -> Path:
        d = self.path / "artifacts"
        d.mkdir(exist_ok=True)
        return d

    def load(self) -> dict:
        if not self.spec_path().is_file():
            raise WorkflowError(f"missing workflow spec {self.spec_path()}")
        spec = yaml.safe_load(self.spec_path().read_text()) or {}
        st = json.loads(self.state_path().read_text()) if self.state_path().is_file() else {}
        return {"spec": spec, "state": st}

    def save_state(self, state: dict) -> None:
        tmp = self.state_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        tmp.replace(self.state_path())

    def init_state(self, spec: dict) -> dict:
        nodes = {}
        for n in spec["nodes"]:
            nodes[n["id"]] = {
                "role": n["role"],
                "depends_on": list(n.get("depends_on") or []),
                "status": "pending",
                "attempts": 0,
                "artifact": None,
                "evidence": None,
                "last_error": None,
                "updated_at": _now(),
            }
        st = {
            "schema": SCHEMA,
            "workflow_id": self.id,
            "created_at": _now(),
            "updated_at": _now(),
            "status": "pending",
            "nodes": nodes,
            "checkpoint_seq": 0,
        }
        self.save_state(st)
        return st


def _deps_ready(node: dict, nodes: dict) -> bool:
    for d in node["depends_on"]:
        if nodes[d]["status"] != "done":
            return False
    return True


def _upstream_artifacts(nodes: dict, depends: list[str]) -> list[dict]:
    out = []
    for d in depends:
        art = nodes[d].get("artifact")
        if not art:
            raise WorkflowError(f"missing upstream artifact from {d}")
        out.append(art)
    return out


def _run_research(_cfg: Config, node: dict, ctx: dict) -> dict:
    nid = node["id"]
    if node.get("inject_fail_once") and node.get("_fail_used") is not True:
        node["_fail_used"] = True
        raise WorkflowError("injected research failure (demo)")
    payload = {
        "node_id": nid,
        "finding": ctx.get("findings", {}).get(nid, f"synthetic finding for {nid}"),
        "generated_at": _now(),
    }
    path = ctx["artifact_dir"] / f"{nid}.json"
    path.write_text(json.dumps(payload, indent=2))
    return {"artifact": {"path": str(path), "finding": payload["finding"]}, "evidence": payload}


def _run_join(_cfg: Config, node: dict, ctx: dict) -> dict:
    nodes = ctx["nodes"]
    parts = _upstream_artifacts(nodes, node["depends_on"])
    merged = {"joined_from": [p["finding"] for p in parts], "at": _now()}
    path = ctx["artifact_dir"] / "join.json"
    path.write_text(json.dumps(merged, indent=2))
    return {"artifact": {"path": str(path), "merged": merged}, "evidence": merged}


def _run_dispatch_node(cfg: Config, node: dict, ctx: dict) -> dict:
    params = node.get("dispatch") or {}
    task_id = params["task_id"]
    repo = params["repo"]
    verify = params.get("verify", f"{sys.executable} -m pytest -q -p no:cacheprovider")
    findings = []
    for dep in node.get("depends_on") or []:
        art = ctx["nodes"][dep].get("artifact") or {}
        if art.get("finding"):
            findings.append(art["finding"])
        if art.get("merged"):
            findings.extend(art["merged"].get("joined_from", []))
    prompt = params.get("prompt", "implement from verified research")
    if findings:
        prompt += "\n\nVerified upstream findings:\n" + "\n".join(f"- {x}" for x in findings)
    runner = ctx.get("runner")
    res = dispatch(
        cfg,
        task_id=task_id,
        task_type=params.get("task_type", "coding"),
        repo=repo,
        prompt=prompt,
        verify=verify,
        runner=runner,
        worktree_root=ctx.get("worktree_root"),
    )
    if res.get("status") != "done":
        raise WorkflowError(f"dispatch not done: {res.get('status')} {res.get('exit_state')}")
    return {
        "artifact": {"task_id": task_id, "commit": res.get("commit"), "worktree": res.get("worktree")},
        "evidence": res.get("verify"),
    }


def _run_lesson(cfg: Config, node: dict, ctx: dict) -> dict:
    life: Lifecycle = ctx["lifecycle"]
    params = node.get("lesson") or {}
    task_id = params.get("from_task")
    summary = params.get("summary")
    if task_id:
        st = TaskStore(cfg).get(task_id).state
        last = (st.get("tests") or [])[-1] if st.get("tests") else {}
        if not summary:
            summary = (
                f"Task {task_id} ended {st.get('exit_state')}; "
                f"last test: {last.get('summary', 'n/a')}"
            )
    if not summary:
        raise WorkflowError("lesson node requires summary or from_task")
    out = capture_remember(
        life,
        project_query=params.get("project", "Agent OS"),
        text=summary,
        kind=params.get("kind", "lesson"),
        session=f"workflow:{ctx['workflow_id']}",
    )
    if out.get("status") != "captured":
        raise WorkflowError(out.get("reason", "lesson capture refused"))
    return {"artifact": out, "evidence": {"proposal_id": out["proposal_id"]}}


DEFAULT_RUNNERS: dict[str, NodeRunner] = {
    "research": _run_research,
    "join": _run_join,
    "coding": _run_dispatch_node,
    "lesson": _run_lesson,
}


def _execute_node(cfg: Config, store: WorkflowStore, node_id: str, runners: dict[str, NodeRunner], ctx: dict) -> None:
    doc = store.load()
    spec, st = doc["spec"], doc["state"]
    node_spec = next(n for n in spec["nodes"] if n["id"] == node_id)
    nst = st["nodes"][node_id]
    if nst["status"] == "done":
        return
    if not _deps_ready(nst, st["nodes"]):
        raise WorkflowError(f"node {node_id} dependencies not satisfied")
    role = nst["role"]
    runner = runners.get(role)
    if not runner:
        raise WorkflowError(f"no runner for role {role}")
    nst["status"] = "running"
    nst["attempts"] += 1
    nst["updated_at"] = _now()
    store.save_state(st)
    try:
        merged = {**node_spec, **nst}
        result = runner(cfg, merged, ctx)
        nst["status"] = "done"
        nst["artifact"] = result.get("artifact")
        nst["evidence"] = result.get("evidence")
        nst["last_error"] = None
    except Exception as exc:
        nst["status"] = "failed"
        nst["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        st["updated_at"] = _now()
        st["checkpoint_seq"] += 1
        store.save_state(st)


def run_workflow(
    cfg: Config,
    workflow_id: str,
    *,
    max_parallel: int = 2,
    runners: dict[str, NodeRunner] | None = None,
    lifecycle: Lifecycle | None = None,
    runner=None,
    worktree_root: Path | None = None,
    resume: bool = False,
) -> dict:
    store = WorkflowStore(workflow_id)
    doc = store.load()
    spec = doc["spec"]
    if not resume or not doc["state"]:
        store.init_state(spec)
        doc = store.load()
    st = doc["state"]
    runners = {**DEFAULT_RUNNERS, **(runners or {})}
    ctx = {
        "workflow_id": workflow_id,
        "artifact_dir": store.artifact_dir(),
        "nodes": st["nodes"],
        "lifecycle": lifecycle,
        "runner": runner,
        "worktree_root": worktree_root,
        "findings": spec.get("findings", {}),
    }
    lock = threading.Lock()

    def refresh_nodes():
        with lock:
            ctx["nodes"] = store.load()["state"]["nodes"]

    def _pending_nodes(nodes: dict) -> list[str]:
        return [nid for nid, n in nodes.items() if n["status"] == "pending"]

    pending = _pending_nodes(st["nodes"])

    while pending:
        ready = []
        nodes = store.load()["state"]["nodes"]
        for nid in pending:
            n = nodes[nid]
            if n["status"] != "pending":
                continue
            if _deps_ready(n, nodes):
                ready.append(nid)
        if not ready:
            failed = [n for n, v in store.load()["state"]["nodes"].items() if v["status"] == "failed"]
            if failed:
                st = store.load()["state"]
                st["status"] = "blocked"
                store.save_state(st)
                return {"workflow_id": workflow_id, "status": "blocked", "failed_nodes": failed, "state": st}
            raise WorkflowError("workflow deadlock: no runnable nodes")
        batch = ready[:max_parallel]
        errors = []
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {
                pool.submit(_execute_node, cfg, store, nid, runners, ctx): nid for nid in batch
            }
            for fut in as_completed(futures):
                nid = futures[fut]
                try:
                    fut.result()
                    refresh_nodes()
                except Exception as exc:
                    errors.append((nid, str(exc)))
                    refresh_nodes()
        pending = _pending_nodes(store.load()["state"]["nodes"])
        if errors and all(store.load()["state"]["nodes"][e[0]]["status"] == "failed" for e in errors):
            st = store.load()["state"]
            st["status"] = "blocked"
            store.save_state(st)
            return {"workflow_id": workflow_id, "status": "blocked", "failed_nodes": [e[0] for e in errors],
                    "errors": errors, "state": st}

    st = store.load()["state"]
    st["status"] = "done"
    store.save_state(st)
    return {"workflow_id": workflow_id, "status": "done", "state": st}


def repair_node(workflow_id: str, node_id: str) -> dict:
    """Mark a failed node pending for bounded retry (does not reset completed siblings)."""
    store = WorkflowStore(workflow_id)
    st = store.load()["state"]
    if node_id not in st["nodes"]:
        raise WorkflowError(f"unknown node {node_id}")
    n = st["nodes"][node_id]
    if n["status"] not in ("failed", "blocked"):
        raise WorkflowError(f"node {node_id} is not failed")
    n["status"] = "pending"
    n["last_error"] = None
    st["status"] = "running"
    st["updated_at"] = _now()
    store.save_state(st)
    return {"workflow_id": workflow_id, "node_id": node_id, "status": "pending"}


def workflow_status(workflow_id: str) -> dict:
    store = WorkflowStore(workflow_id)
    doc = store.load()
    st = doc["state"] or store.init_state(doc["spec"])
    return {
        "schema": SCHEMA,
        "workflow_id": workflow_id,
        "status": st.get("status", "pending"),
        "nodes": {k: {kk: vv for kk, vv in v.items() if kk != "artifact"} for k, v in st["nodes"].items()},
        "checkpoint_seq": st.get("checkpoint_seq", 0),
        "updated_at": st.get("updated_at"),
    }