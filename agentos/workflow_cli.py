"""CLI for dependency-aware workflows."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

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


def run(cfg, args):
    try:
        life = Lifecycle(cfg)
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
        else:
            raise WorkflowError("unknown workflow action")
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") in ("done", "initialized", "pending", "running") else 2
    except (WorkflowError, ValueError, OSError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)[:300]}), file=sys.stderr)
        return 2