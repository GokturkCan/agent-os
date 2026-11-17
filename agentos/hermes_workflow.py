"""Natural-language entry to operational workflow graphs (Hermes contract).

Builds deterministic workflow specs from user text; execution evidence lives under
state/workflows/ and taskstate — not in model prose.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .knowledge_lifecycle import Lifecycle
from .workflow_graph import WorkflowStore, WorkflowError, repair_node, run_workflow, workflow_status

PLAN_SCHEMA = "agentos.hermes-workflow-plan.v1"
EXEC_SCHEMA = "agentos.hermes-workflow-execute.v1"
CONTINUE_SCHEMA = "agentos.hermes-workflow-continue.v1"


def _slug_id(text: str, project_id: str) -> str:
    digest = hashlib.sha256(f"{project_id}\n{text.strip().lower()}".encode()).hexdigest()[:10]
    return f"nl-{digest}"


def _dual_research(text: str) -> bool:
    t = text.casefold()
    if re.search(
        r"\btwo\s+(independent\s+)?(approaches?|methods?|options?|strategies?|paths?|ways?|analyses?|tasks?|research)",
        t,
    ):
        return True
    if re.search(r"\bresearch\s+two\b", t):
        return True
    return any(
        p in t
        for p in (
            "two independent",
            "two research",
            "parallel research",
            "both research",
            "run two",
            "compare two",
            "two analysis",
            "compare them",
            "compare both",
        )
    )


def _research_task_descriptions(body: str, dual: bool) -> dict[str, str]:
    """Planning-time branch objectives — not verified findings (produced by research nodes)."""
    scope = body.strip()[:480]
    if dual:
        return {
            "research-a": f"[task] Research branch A — first approach for: {scope}",
            "research-b": f"[task] Research branch B — second approach for: {scope}",
        }
    return {"research-a": f"[task] Research branch — objective: {scope}"}


_BROAD_IMPL = re.compile(r"(?i)\b(implement|prototype|prototype\.|build|refactor)\b")
_SCOPED_TARGET = re.compile(
    r"(?i)(fixture[s]?/|/[\w./-]+\.(py|rs|go|ts|tsx|js)|\bmodule\s+[\w.]+\b|"
    r"\bfile\s+[\w./-]+|\bin\s+[\w./-]+\.(py|md)\b|worktree-only|isolated\s+repo)"
)


def _is_control_plane_repo(cfg: Config, repo: Path) -> bool:
    try:
        return repo.resolve() == cfg.root.resolve()
    except OSError:
        return False


def _resolve_implementation_repo(cfg: Config, project: dict, repo: Path, body: str) -> Path:
    registered = []
    for r in project.get("repositories") or []:
        try:
            p = Path(r).resolve()
            if p.is_dir():
                registered.append(p)
        except OSError:
            continue
    broad = _BROAD_IMPL.search(body) and not _SCOPED_TARGET.search(body)
    if _is_control_plane_repo(cfg, repo) and broad:
        for candidate in registered:
            if not _is_control_plane_repo(cfg, candidate):
                return candidate
        raise ValueError(
            "broad implementation against the Agent OS control-plane repository is refused; "
            "use a project-registered implementation repository or name a concrete scoped target "
            "(fixture path, module, or file) in the request"
        )
    if registered and repo not in registered and _is_control_plane_repo(cfg, repo):
        return registered[0]
    return repo


def _coding_prompt(body: str, repo: Path) -> str:
    return (
        "Scope: change only files inside the assigned git worktree for this task. "
        "Do not modify Agent OS policy, skills, or other repositories. "
        "Use verified upstream join artifacts as evidence; treat the user objective below as "
        "planning context, not as pre-verified fact.\n\n"
        f"User objective:\n{body[:3600]}"
    )


def plan_workflow_request(
    cfg: Config,
    *,
    text: str,
    project_query: str,
    repo: str | Path,
    objective: str | None = None,
    workflow_id: str | None = None,
    task_id: str | None = None,
    lifecycle: Lifecycle | None = None,
) -> dict[str, Any]:
    """Map NL request → workflow spec (no execution)."""
    life = lifecycle or Lifecycle(cfg)
    resolved = life.projects.resolve(project_query)
    if resolved["status"] != "matched":
        return {
            "schema": PLAN_SCHEMA,
            "status": resolved["status"],
            "candidates": resolved.get("candidates", []),
        }
    project = resolved["project"]
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise ValueError(f"repo not found: {repo}")
    body = (objective or text or "").strip()
    if not body:
        raise ValueError("workflow request text required")
    dual = _dual_research(body)
    findings = _research_task_descriptions(body, dual)
    impl_repo = _resolve_implementation_repo(cfg, project, repo, body)
    wf_id = workflow_id or _slug_id(body, project["id"])
    tid = task_id or f"wf-{wf_id[-8:]}"
    verify = f"{sys.executable} -m pytest -q -p no:cacheprovider"
    nodes: list[dict] = [
        {"id": "research-a", "role": "research", "depends_on": []},
    ]
    if dual:
        nodes.append({"id": "research-b", "role": "research", "depends_on": []})
        join_deps = ["research-a", "research-b"]
    else:
        join_deps = ["research-a"]
    nodes += [
        {"id": "join", "role": "join", "depends_on": join_deps},
        {
            "id": "implement",
            "role": "coding",
            "depends_on": ["join"],
            "dispatch": {
                "task_id": tid,
                "repo": str(impl_repo),
                "verify": verify,
                "prompt": _coding_prompt(body, impl_repo),
            },
        },
        {
            "id": "lesson",
            "role": "lesson",
            "depends_on": ["implement"],
            "lesson": {"project": project["id"], "from_task": tid, "kind": "lesson"},
        },
    ]
    spec = {"findings": findings, "nodes": nodes, "meta": {"source_text": body[:500], "project_id": project["id"]}}
    return {
        "schema": PLAN_SCHEMA,
        "status": "planned",
        "workflow_id": wf_id,
        "project_id": project["id"],
        "project_name": project["name"],
        "repository": str(impl_repo),
        "requested_repository": str(repo),
        "spec": spec,
        "planned_nodes": [n["id"] for n in nodes],
        "dual_research": dual,
    }


def execute_workflow_request(
    cfg: Config,
    *,
    text: str,
    project_query: str,
    repo: str | Path,
    objective: str | None = None,
    workflow_id: str | None = None,
    max_parallel: int = 2,
    resume: bool = False,
    runner=None,
    worktree_root: Path | None = None,
    lifecycle: Lifecycle | None = None,
) -> dict[str, Any]:
    life = lifecycle or Lifecycle(cfg)
    plan = plan_workflow_request(
        cfg,
        text=text,
        project_query=project_query,
        repo=repo,
        objective=objective,
        workflow_id=workflow_id,
        lifecycle=life,
    )
    if plan.get("status") != "planned":
        return {**plan, "schema": EXEC_SCHEMA, "execution": None}
    wf_id = plan["workflow_id"]
    store = WorkflowStore(wf_id)
    if not resume or not store.spec_path().is_file():
        store.spec_path().write_text(yaml.safe_dump(plan["spec"], sort_keys=False))
        store.init_state(plan["spec"])
    execution = run_workflow(
        cfg,
        wf_id,
        max_parallel=max_parallel,
        lifecycle=life,
        runner=runner,
        worktree_root=worktree_root,
        resume=resume,
    )
    checkpoint = workflow_status(wf_id)
    return {
        "schema": EXEC_SCHEMA,
        "status": execution["status"],
        "workflow_id": wf_id,
        "project_id": plan["project_id"],
        "planned_nodes": plan["planned_nodes"],
        "execution": execution,
        "checkpoint": checkpoint,
        "evidence": {
            "workflow_state": str(store.state_path()),
            "workflow_spec": str(store.spec_path()),
            "checkpoint_seq": checkpoint.get("checkpoint_seq"),
        },
        "verify_command": f"agentos workflow status {wf_id}",
    }


def continue_workflow(
    cfg: Config,
    *,
    workflow_id: str,
    project_query: str | None = None,
    max_parallel: int = 2,
    runner=None,
    worktree_root: Path | None = None,
    lifecycle: Lifecycle | None = None,
) -> dict[str, Any]:
    before = workflow_status(workflow_id)
    if before.get("status") == "blocked":
        failed = [n for n, v in before["nodes"].items() if v["status"] == "failed"]
        for nid in failed:
            repair_node(workflow_id, nid)
    life = lifecycle or Lifecycle(cfg)
    execution = run_workflow(
        cfg,
        workflow_id,
        max_parallel=max_parallel,
        lifecycle=life,
        runner=runner,
        worktree_root=worktree_root,
        resume=True,
    )
    after = workflow_status(workflow_id)
    out: dict[str, Any] = {
        "schema": CONTINUE_SCHEMA,
        "status": execution["status"],
        "workflow_id": workflow_id,
        "before": before,
        "after": after,
        "execution": execution,
        "authoritative": True,
    }
    if project_query:
        from .hermes_knowledge import where_stopped

        repo = None
        try:
            doc = WorkflowStore(workflow_id).load()
            for n in doc["spec"]["nodes"]:
                if n.get("role") == "coding":
                    repo = n.get("dispatch", {}).get("repo")
                    break
        except (WorkflowError, KeyError, TypeError):
            repo = None
        if repo:
            out["continuity"] = where_stopped(cfg, life, project_query=project_query, repo=repo)
    return out