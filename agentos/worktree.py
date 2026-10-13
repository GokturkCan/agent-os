"""Git worktree isolation with a single-owner lease per checkout.

The lease lives in the worktree's private git dir
(`git rev-parse --git-path agentos-lease.json`), so it never shows up as an
untracked file in the checkout and is unique per worktree.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class LeaseError(Exception):
    pass


def git(cwd: Path | str, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def create(repo: Path | str, task_id: str, root: Path | str, base: str = "HEAD") -> Path:
    repo, root = Path(repo), Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{repo.name}-{task_id}"
    git(repo, "worktree", "add", "-b", f"agentos/{task_id}", str(path), base)
    return path


def _lease_path(worktree: Path | str) -> Path:
    p = Path(git(worktree, "rev-parse", "--git-path", "agentos-lease.json"))
    return p if p.is_absolute() else Path(worktree) / p


def acquire(worktree: Path | str, worker: str, task_id: str) -> dict:
    lease = _lease_path(worktree)
    rec = {"worker": worker, "task_id": task_id,
           "acquired_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}
    try:
        fd = os.open(lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        held = json.loads(lease.read_text())
        if held.get("worker") == worker and held.get("task_id") == task_id:
            return held
        raise LeaseError(f"checkout {worktree} already leased to {held.get('worker')} "
                         f"for {held.get('task_id')}") from None
    with os.fdopen(fd, "w") as fh:
        json.dump(rec, fh)
    return rec


def holder(worktree: Path | str) -> dict | None:
    lease = _lease_path(worktree)
    return json.loads(lease.read_text()) if lease.exists() else None


def release(worktree: Path | str, worker: str):
    lease = _lease_path(worktree)
    if not lease.exists():
        return
    held = json.loads(lease.read_text())
    if held.get("worker") != worker:
        raise LeaseError(f"{worker} cannot release lease held by {held.get('worker')}")
    lease.unlink()


def is_clean(worktree: Path | str) -> bool:
    return git(worktree, "status", "--porcelain") == ""


def remove(repo: Path | str, worktree: Path | str):
    """Remove a finished worktree. Refuses if leased or dirty (no --force)."""
    if holder(worktree):
        raise LeaseError("worktree still leased")
    if not is_clean(worktree):
        raise LeaseError("worktree has uncommitted changes")
    git(repo, "worktree", "remove", str(worktree))


# ------------------------------------------------ code-intel freshness
def index_stamp(worktree: Path | str) -> dict:
    """Identity of the code state a derived index (Serena/codebase-memory/
    repomix pack) was built from: worktree path + HEAD + dirty-diff hash."""
    diff = git(worktree, "diff", "HEAD")
    import hashlib
    return {"worktree": str(Path(worktree).resolve()), "head": git(worktree, "rev-parse", "HEAD"),
            "dirty_sha256": hashlib.sha256(diff.encode()).hexdigest() if diff else None}


def is_fresh(worktree: Path | str, stamp: dict) -> bool:
    return index_stamp(worktree) == stamp
