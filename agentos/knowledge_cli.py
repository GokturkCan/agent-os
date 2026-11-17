"""Hermes-facing lifecycle CLI. Intentionally no approve/apply command."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

from .knowledge import GateError
from .knowledge_lifecycle import Lifecycle


def add_parser(sub):
    parser = sub.add_parser("knowledge", help="project-aware capture, context and reviewer handoffs")
    actions = parser.add_subparsers(dest="knowledge_action", required=True)
    projects = actions.add_parser("projects", help="derive project identities from canonical wiki notes")
    projects.add_argument("query", nargs="?")
    capture = actions.add_parser("capture", help="stage an explicitly authorized structured JSON record")
    capture.add_argument("--input", required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--project")
    for action in ("show", "ready", "export", "reconcile"):
        actions.add_parser(action).add_argument("id")
    reject = actions.add_parser("reject")
    reject.add_argument("id"); reject.add_argument("--reason", required=True)
    context = actions.add_parser("context")
    context.add_argument("--project", required=True)
    context.add_argument("--objective", required=True)
    context.add_argument("--budget", type=int, default=8000)
    context.add_argument("--worker", choices=["claude_code", "codex"], default="claude_code")
    context.add_argument("--profile", default="coder")
    dispatch = actions.add_parser("dispatch", help="prepare scoped dispatch; execution requires --execute")
    for field in ("project", "task-id", "repo", "objective", "verify"):
        dispatch.add_argument("--"+field, required=True)
    dispatch.add_argument("--execute", action="store_true", help="use existing dispatcher including its normal task-branch commit behavior")
    ingest = actions.add_parser("ingest-result")
    ingest.add_argument("--project", required=True); ingest.add_argument("--input", required=True)
    changes = actions.add_parser("changes")
    changes.add_argument("--project", required=True); changes.add_argument("--since", required=True)
    actions.add_parser("navigation", help="write reviewable Markdown outside the canonical vault")
    inspect = actions.add_parser("inspect", help="read-only repository and Markdown inspection")
    inspect.add_argument("--repo", required=True)
    onboard = actions.add_parser("onboard", help="stage a reviewable project onboarding proposal")
    onboard.add_argument("--repo", required=True)
    onboard.add_argument("--authorized", action="store_true",
                         help="explicit authorization to stage a DRAFT project proposal")
    onboard.add_argument("--scope", default=None)
    status = actions.add_parser("status", help="read-only project status and worker/task continuity")
    status.add_argument("--project", required=True)
    status.add_argument("--repo", required=True)
    cont = actions.add_parser("continue", help="prepare a bounded read-only continuation context package")
    cont.add_argument("--project", required=True)
    cont.add_argument("--repo", required=True)
    cont.add_argument("--objective", required=True)
    cont.add_argument("--budget", type=int, default=12000)
    cont.add_argument("--worker", choices=["claude_code", "codex"], default="claude_code")
    cont.add_argument("--profile", default="coder")
    remember = actions.add_parser(
        "remember",
        help="Hermes contract: NL remember → verified DRAFT proposal (no vault write)",
    )
    remember.add_argument("--project", required=True, help="project id, name, or alias")
    remember.add_argument("--text", required=True, help="concise durable summary to capture")
    remember.add_argument("--kind", choices=[
        "idea", "hypothesis", "research_question", "decision", "experiment", "lesson",
        "rejected_alternative", "blocker", "follow_up",
    ])
    remember.add_argument("--session", help="Hermes session id for provenance (optional)")
    where = actions.add_parser(
        "where-stopped",
        help="Hermes contract: authoritative continuity JSON (status + continuation + recall)",
    )
    where.add_argument("--project", required=True)
    where.add_argument("--repo", help="defaults to first registered project repository")
    where.add_argument("--objective", help="continuation objective (optional)")


def _input(path):
    p = Path(path)
    if p.stat().st_size > 64_000: raise ValueError("input exceeds 64KB; provide a bounded summary")
    value = json.loads(p.read_text())
    if not isinstance(value, dict): raise ValueError("input must be a structured JSON object")
    return value


def run(cfg, args):
    try:
        life = Lifecycle(cfg)
        action = args.knowledge_action
        if action == "projects":
            result = life.projects.resolve(args.query) if args.query else life.projects.list()
        elif action == "capture": result = life.capture(**_input(args.input))
        elif action == "list": result = life.list(args.project)
        elif action in ("show", "ready", "export", "reconcile"): result = getattr(life, action)(args.id)
        elif action == "reject": result = life.reject(args.id, args.reason)
        elif action == "context": result = life.context(args.project, args.objective, budget=args.budget,
                                                        worker=args.worker, profile=args.profile)
        elif action == "dispatch":
            result = life.dispatch_task(args.project, args.task_id, args.repo, args.objective,
                                        verify=args.verify, dry_run=not args.execute)
        elif action == "ingest-result": result = life.ingest_result(args.project, **_input(args.input))
        elif action == "navigation": result = {"preview": life.navigation()}
        elif action == "inspect":
            from .project_onboarding import inspect_repository
            result = inspect_repository(args.repo, projects=life.projects)
        elif action == "onboard":
            from .project_onboarding import propose_onboarding
            result = propose_onboarding(life, args.repo, authorized=args.authorized, scope=args.scope)
        elif action == "status":
            from .project_continuity import project_status
            from .config import Config
            result = project_status(cfg, life, args.project, args.repo)
        elif action == "continue":
            from .project_continuity import continuation_package
            result = continuation_package(cfg, life, args.project, args.repo, args.objective,
                                          budget=args.budget, worker=args.worker, profile=args.profile)
        elif action == "remember":
            from .hermes_knowledge import capture_remember
            result = capture_remember(
                life,
                project_query=args.project,
                text=args.text,
                kind=args.kind,
                session=args.session,
            )
            if result.get("status") != "captured":
                print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
                return 2
        elif action == "where-stopped":
            from .hermes_knowledge import where_stopped
            result = where_stopped(cfg, life, project_query=args.project, repo=args.repo,
                                   objective=args.objective)
            if result.get("status") != "ok":
                print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
                return 2
        elif action == "changes":
            def instant(value):
                stamp=datetime.fromisoformat(value.replace("Z", "+00:00"))
                return (stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
            try:since = instant(args.since)
            except ValueError:raise ValueError("since must be an ISO timestamp") from None
            pid = life._project(args.project)["id"]
            result = {"project_id": pid, "since": since.isoformat(),
                      "proposals": [{"id":p["id"],"state":p["state"],"updated_at":p["updated_at"]}
                                    for p in life.list(args.project)
                                    if instant(p["updated_at"]) >= since],
                      "canonical_notes": [{"path":rel,"updated":str(fm.get("updated")),
                                           "precision":"day"} for rel,fm,_ in life.projects.pages()
                                          if fm.get("project_id")==pid and str(fm.get("updated", ""))>=args.since[:10]],
                      "note":"Only explicit timestamps; no invented previous-session history. Canonical updated dates have day precision."}
        else: raise ValueError("unknown knowledge action")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0
    except (ValueError, TypeError, KeyError, OSError, GateError, yaml.YAMLError) as exc:
        # Do not echo input records or worker output, which may contain secrets.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        print(json.dumps({"status":"refused", "reason":message[:240]}), file=sys.stderr)
        return 2
