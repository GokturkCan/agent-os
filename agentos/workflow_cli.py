"""CLI for dependency-aware workflows."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from .hermes_workflow import continue_workflow, execute_workflow_request, plan_workflow_request
from .knowledge_lifecycle import Lifecycle
from .workflow_graph import WorkflowStore, WorkflowError, repair_node, run_workflow, workflow_status


def add_parser(sub):
    p = sub.add_parser("workflow", help="dependency-aware multi-step workflows (operational state only)")
    actions = p.add_subparsers(dest="workflow_action", required=True)
    init = actions.add_parser("init", help="create workflow from YAML spec")
    init.add_argument("id")
    init.add_argument("--spec", required=True, help="workflow YAML file")
    for name in ("run", "resume"):
        a = actions.add_parser(name)
        a.add_argument("id")
        a.add_argument("--max-parallel", type=int, default=2)
    actions.add_parser("status").add_argument("id")
    repair = actions.add_parser("repair-node", help="retry a failed node without resetting siblings")
    repair.add_argument("id")
    repair.add_argument("node")
    req = actions.add_parser(
        "request",
        help="Hermes contract: NL text → planned graph → execute (evidence in state/workflows/)",
    )
    req.add_argument("--text", required=True, help="natural-language workflow objective")
    req.add_argument("--project", required=True, help="project id, name, or alias")
    req.add_argument("--repo", required=True, help="absolute repository path for coding node")
    req.add_argument("--workflow-id", help="optional stable slug; default derived from text")
    req.add_argument("--max-parallel", type=int, default=2)
    req.add_argument("--resume", action="store_true", help="resume existing workflow checkpoint")
    plan = actions.add_parser("plan", help="plan only (no execution)")
    plan.add_argument("--text", required=True)
    plan.add_argument("--project", required=True)
    plan.add_argument("--repo", required=True)
    plan.add_argument("--workflow-id")
    cont = actions.add_parser("continue", help="resume blocked/failed workflows (repair failed nodes)")
    cont.add_argument("id")
    cont.add_argument("--project", help="optional: attach where-stopped continuity")
    cont.add_argument("--max-parallel", type=int, default=2)


def run(cfg, args):
    try:
        life = Lifecycle(cfg)
        life_kw = {"lifecycle": life}
        if args.workflow_action == "init":
            spec = yaml.safe_load(Path(args.spec).read_text())
            store = WorkflowStore(args.id)
            store.spec_path().write_text(yaml.safe_dump(spec, sort_keys=False))
            st = store.init_state(spec)
            result = {"workflow_id": args.id, "status": "initialized", "nodes": list(st["nodes"])}
        elif args.workflow_action == "run":
            result = run_workflow(cfg, args.id, max_parallel=args.max_parallel, lifecycle=life)
        elif args.workflow_action == "resume":
            result = run_workflow(cfg, args.id, max_parallel=args.max_parallel, lifecycle=life, resume=True)
        elif args.workflow_action == "status":
            result = workflow_status(args.id)
        elif args.workflow_action == "repair-node":
            result = repair_node(args.id, args.node)
        elif args.workflow_action == "plan":
            result = plan_workflow_request(
                cfg,
                text=args.text,
                project_query=args.project,
                repo=args.repo,
                workflow_id=args.workflow_id,
                **life_kw,
            )
        elif args.workflow_action == "request":
            result = execute_workflow_request(
                cfg,
                text=args.text,
                project_query=args.project,
                repo=args.repo,
                workflow_id=args.workflow_id,
                max_parallel=args.max_parallel,
                resume=args.resume,
                **life_kw,
            )
        elif args.workflow_action == "continue":
            result = continue_workflow(
                cfg,
                workflow_id=args.id,
                project_query=args.project,
                max_parallel=args.max_parallel,
                **life_kw,
            )
        else:
            raise WorkflowError("unknown workflow action")
        print(json.dumps(result, indent=2, default=str))
        ok = result.get("status") in ("done", "initialized", "pending", "running", "planned")
        return 0 if ok else 2
    except (WorkflowError, ValueError, OSError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)[:300]}), file=sys.stderr)
        return 2