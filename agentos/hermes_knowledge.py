"""Deterministic Hermes-facing knowledge contracts (capture + continuity).

Success is defined by Agent OS operational state, not model narrative.
"""
from __future__ import annotations

import os
import re
from typing import Any

from .config import Config
from .knowledge_lifecycle import Lifecycle
from .project_continuity import continuation_package, project_status
from .recall import recall
from .taskstate import TaskStore

PROPOSAL_ID = re.compile(r"^kp-[a-f0-9]{24}$")


def infer_kind(text: str) -> str:
    t = text.casefold()
    if any(w in t for w in ("we decided", "decision:", "decided to")):
        return "decision"
    if "research question" in t or t.strip().endswith("?"):
        return "research_question"
    if "experiment" in t:
        return "experiment"
    if "lesson" in t or "learned" in t:
        return "lesson"
    return "idea"


def verify_proposal_on_disk(life: Lifecycle, proposal_id: str) -> bool:
    if not PROPOSAL_ID.fullmatch(proposal_id):
        return False
    try:
        record = life.show(proposal_id)
    except (ValueError, OSError, KeyError):
        return False
    return record.get("id") == proposal_id and record.get("state") in (
        "DRAFT",
        "READY_FOR_REVIEW",
        "APPROVED",
        "COMMITTED",
        "REJECTED",
    )


def capture_remember(
    life: Lifecycle,
    *,
    project_query: str,
    text: str,
    kind: str | None = None,
    session: str | None = None,
) -> dict[str, Any]:
    summary = (text or "").strip()
    if not summary:
        raise ValueError("remember text required")
    if len(summary) > 2000:
        raise ValueError("remember text exceeds 2000 characters")
    kind = kind or infer_kind(summary)
    session = (session or os.environ.get("HERMES_SESSION_ID") or os.environ.get("AGENTOS_HERMES_SESSION")
               or "hermes:nl-capture")
    session = re.sub(r"[^\w.:-]", "-", session)[:120]
    evidence = [{"kind": "user_statement", "locator": f"hermes:remember:{session}"}]
    origin = {"actor": "hermes", "kind": "user_statement", "session": session}
    record = life.capture(
        project=project_query,
        kind=kind,
        summary=summary,
        evidence=evidence,
        authorized=True,
        origin=origin,
        confidence="user_statement",
    )
    pid = record["id"]
    verified = verify_proposal_on_disk(life, pid)
    if not verified:
        return {
            "schema": "agentos.hermes-knowledge-capture.v1",
            "status": "refused",
            "reason": "proposal not found in operational state after capture",
            "proposal_id": pid,
            "verified_on_disk": False,
        }
    return {
        "schema": "agentos.hermes-knowledge-capture.v1",
        "status": "captured",
        "proposal_id": pid,
        "state": record["state"],
        "kind": kind,
        "project_id": record["project_id"],
        "verified_on_disk": True,
        "verify_command": f"agentos knowledge show {pid}",
    }


def learn_from_task(
    life: Lifecycle,
    *,
    task_id: str,
    project_query: str,
    session: str | None = None,
    extra: str | None = None,
) -> dict[str, Any]:
    """Turn verified task evidence into a lesson proposal (operational capture only)."""
    st = TaskStore(life.cfg).get(task_id).state
    tests = st.get("tests") or []
    last = tests[-1] if tests else {}
    parts = [
        f"Task {task_id} exit={st.get('exit_state') or 'open'}.",
        f"Last verification: {last.get('summary', 'n/a')}.",
    ]
    if extra:
        parts.append(extra.strip())
    text = " ".join(parts)
    return capture_remember(
        life,
        project_query=project_query,
        text=text,
        kind="lesson",
        session=session or f"learn:{task_id}",
    )


def where_stopped(
    cfg: Config,
    life: Lifecycle,
    *,
    project_query: str,
    repo: str | None = None,
    objective: str | None = None,
) -> dict[str, Any]:
    resolved = life.projects.resolve(project_query)
    if resolved["status"] != "matched":
        return {
            "schema": "agentos.where-stopped.v1",
            "status": resolved["status"],
            "candidates": resolved.get("candidates", []),
            "project_status": None,
        }
    project = resolved["project"]
    repositories = project.get("repositories") or []
    if repo is None:
        if not repositories:
            raise ValueError("project has no registered repository; pass --repo")
        repo = repositories[0]
    obj = (objective or "Where did we stop? Report task state, blockers, and pending proposals.").strip()
    status = project_status(cfg, life, project["id"], repo)
    cont = continuation_package(cfg, life, project["id"], repo, obj, budget=48_000)
    recall_result = recall(cfg, project["name"], top=3)
    return {
        "schema": "agentos.where-stopped.v1",
        "status": "ok",
        "project_id": project["id"],
        "project_name": project["name"],
        "repository": str(repo),
        "project_status": status,
        "continuation": cont,
        "recall": {"status": recall_result.get("status"), "results": recall_result.get("results", [])[:3]},
        "authoritative": True,
        "forbidden_substitutes": [
            "find/grep under SecondBrain without agentos knowledge where-stopped",
            "invented proposal paths or kp- IDs",
        ],
    }