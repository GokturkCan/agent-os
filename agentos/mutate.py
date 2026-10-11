"""Structural mutation branch of the canonical entrypoint (bin/hermes-agentos).

A forced mutation request never enters a Hermes loop: it goes straight to the
existing `dispatch()` (routing, worktree, worker, verifier, state, telemetry).
This module only maps the request to dispatch arguments; it adds no policy."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .config import Config
from .dispatch import dispatch

TASK_TYPE = "coding"


def detect_verify(repo: Path) -> str | None:
    """Deterministic default acceptance command; None when nothing is recognisable."""
    pyproject = repo / "pyproject.toml"
    if any((repo / f).exists() for f in ("pytest.ini", "conftest.py", "tox.ini")) or (
            pyproject.exists() and "[tool.pytest" in pyproject.read_text(errors="ignore")):
        return "python3 -m pytest -q"
    if (repo / "package.json").exists():
        return "npm test"
    if list(repo.glob("test*.py")) or list(repo.glob("tests/**/test*.py")):
        return "python3 -m unittest -v"
    return None


def task_id_for(repo: Path, text: str) -> str:
    """Stable per (repo, request): re-running resumes the same task and budgets."""
    return "hermes-" + hashlib.sha1(f"{repo}\0{text}".encode()).hexdigest()[:10]


def run(cfg: Config, text: str, repo: str | Path, *, verify: str | None = None,
        task_id: str | None = None, **dispatch_kw) -> dict:
    repo = Path(repo).resolve()
    verify = verify or detect_verify(repo)
    if not verify:
        return {"task_id": task_id, "status": "not_dispatched", "exit_state": "blocked",
                "trace": [f"no verification command detected in {repo}; set AGENTOS_VERIFY"],
                "next_step": "provide a verification command; Hermes is not used as a fallback"}
    return dispatch(cfg, task_id=task_id or task_id_for(repo, text), task_type=TASK_TYPE,
                    repo=repo, prompt=text, verify=verify, **dispatch_kw)
