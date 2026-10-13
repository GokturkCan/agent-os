"""Durable lessons and the controlled self-improvement gate.

  run -> telemetry -> lesson candidate (vault inbox, evidence) -> capture
      -> knowledge proposal -> independent review -> canonical   (lessons)

  proposal -> isolated change (worktree) -> held-out eval -> independent judge
      -> canary -> promote | rollback                            (config/code)

This module only enforces the gate. It never edits files itself; a
candidate is a git branch/worktree prepared by a worker, and promotion is a
recorded decision a human applies (merge). A candidate that touches a
protected path (judge, held-out evals, permissions, security policy,
promotion criteria) is rejected before any evaluation runs.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT
from .permissions import PROTECTED_POLICY_PATHS, is_protected

MANIFEST = REPO_ROOT / "evals" / "protected-manifest.json"
STAGES = ("proposed", "isolated", "heldout_eval", "judged", "canary", "promoted", "rolled_back",
          "rejected")


class GateViolation(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------- lessons
def write_lesson_candidate(vault_root: Path, run_record: dict, title: str, lesson: str,
                           evidence: list[str]) -> Path:
    """Workers may write lesson candidates into <vault>/inbox/lessons only."""
    d = Path(vault_root) / "inbox" / "lessons"
    d.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")[:60]
    p = d / f"{run_record['run_id']}-{slug}.md"
    p.write_text("\n".join([
        f"# Lesson candidate: {title}", "",
        f"- run_id: {run_record['run_id']}", f"- task_type: {run_record.get('task_type')}",
        f"- worker: {run_record.get('worker')}", f"- exit_state: {run_record.get('exit_state')}",
        f"- recorded: {_now()}", "", "## Lesson", lesson.strip(), "", "## Evidence",
        *[f"- {e}" for e in evidence], ""]))
    return p


def lesson_writes(vault, raw_sha: str, raw_rel: str, title: str, lesson: str, run_id: str,
                  today: str) -> list[dict]:
    page = f"wiki/concepts/{title}.md"
    content = "\n".join([
        "---", "type: concept", f'title: "{title}"', f"created: {today}", f"updated: {today}",
        "status: seed", "tags:", "  - lesson", f'learned_from: "{run_id}"', f'evidence_sha256: "{raw_sha}"',
        "review_state: reviewed", "---", "", f"# {title}", "", lesson.strip(), "",
        f"Provenance: run `{run_id}` → evidence `{raw_rel}`.", ""])
    log = vault.read("wiki/log.md").rstrip() + f"\n\n## {today} — lesson {title}\n\n- Promoted lesson [[{title}]] from run `{run_id}`.\n"
    return [{"path": page, "mode": "create", "content": content},
            {"path": "wiki/log.md", "mode": "replace", "content": log}]


# ------------------------------------------------- protected manifest
# Names that are never policy content (caches, OS metadata); skipped when walking a tree.
_SKIP_DIRS = {"__pycache__", ".pytest_cache"}
_SKIP_FILES = {".DS_Store", "protected-manifest.json"}


def _discover(root: Path, pattern: str):
    """Yield the regular files a protected pattern names, independent of pathlib version.

    `<dir>/**` walks the tree explicitly with os.walk. `Path.glob("**")` is not used because
    it yields only directories on Python 3.11 and files too on 3.13+, which made the manifest
    hash nothing on one and report false drift on the other. Other patterns are a literal path
    or a single-level `*`/`?` glob (stable across versions); "**" anywhere else is rejected.
    """
    if pattern.endswith("/**"):
        for dirpath, dirnames, filenames in os.walk(root / pattern[:-3]):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if name not in _SKIP_FILES and p.suffix != ".pyc" and p.is_file():
                    yield p
    elif "**" in pattern:
        raise ValueError(f"unsupported protected pattern {pattern!r}: '**' only as a trailing '/**'")
    elif any(c in pattern for c in "*?["):
        yield from (p for p in sorted(root.glob(pattern)) if p.is_file() and p.name not in _SKIP_FILES)
    elif (root / pattern).is_file():
        yield root / pattern


def compute_manifest(root: Path = REPO_ROOT) -> dict:
    files = {}
    for pat in PROTECTED_POLICY_PATHS:
        for p in _discover(root, pat):
            files[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def verify_manifest(root: Path = REPO_ROOT) -> list[str]:
    """Return protected files whose content differs from the reviewed manifest."""
    manifest = json.loads((root / "evals" / "protected-manifest.json").read_text())["files"]
    current = compute_manifest(root)
    return sorted(k for k in set(manifest) | set(current) if manifest.get(k) != current.get(k))


# --------------------------------------------------- improvement gate
class Candidate:
    def __init__(self, directory: Path, cid: str):
        self.path = Path(directory) / f"{cid}.json"
        self.id = cid

    @property
    def rec(self) -> dict:
        return json.loads(self.path.read_text())

    def _save(self, rec):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rec, indent=2))

    @classmethod
    def propose(cls, directory: Path, cid: str, producer: str, rationale: str,
                lesson_ref: str | None) -> "Candidate":
        c = cls(directory, cid)
        if c.path.exists():
            raise GateViolation("candidate exists")
        c._save({"id": cid, "producer": producer, "rationale": rationale, "lesson_ref": lesson_ref,
                 "stage": "proposed", "history": [{"stage": "proposed", "at": _now()}]})
        return c

    def _advance(self, expected: str, new: str, **data):
        rec = self.rec
        if rec["stage"] != expected:
            raise GateViolation(f"{self.id}: cannot go {rec['stage']} -> {new} (needs {expected})")
        rec["stage"] = new
        rec["history"].append({"stage": new, "at": _now(), **data})
        rec.update(data)
        self._save(rec)

    def _reject(self, reason: str):
        rec = self.rec
        rec["stage"] = "rejected"
        rec["history"].append({"stage": "rejected", "at": _now(), "reason": reason})
        self._save(rec)

    def isolate(self, branch: str, changed_paths: list[str]):
        bad = [p for p in changed_paths if is_protected(p)]
        if bad:
            self._reject(f"touches protected paths: {bad}")
            raise GateViolation(f"candidate modifies protected paths: {bad}")
        self._advance("proposed", "isolated", branch=branch, changed_paths=changed_paths)

    def heldout_eval(self, passed: bool, report: str, manifest_drift: list[str]):
        if manifest_drift:
            self._reject(f"held-out/judge files drifted: {manifest_drift}")
            raise GateViolation("protected manifest drift — evaluation invalid")
        if not passed:
            self._reject(f"held-out eval failed: {report}")
            return False
        self._advance("isolated", "heldout_eval", eval_report=report)
        return True

    def judge(self, judge: str, verdict: bool, notes: str):
        if judge == self.rec["producer"]:
            raise GateViolation("judge must be independent of the producer")
        if not verdict:
            self._reject(f"judge {judge} rejected: {notes}")
            return False
        self._advance("heldout_eval", "judged", judge=judge, judge_notes=notes)
        return True

    def canary(self, passed: bool, report: str):
        if not passed:
            self._advance("judged", "rolled_back", canary_report=report)
            return False
        self._advance("judged", "canary", canary_report=report)
        return True

    def promote(self, human_approval_ref: str):
        if not human_approval_ref:
            raise GateViolation("promotion requires human approval")
        self._advance("canary", "promoted", human_approval_ref=human_approval_ref)
