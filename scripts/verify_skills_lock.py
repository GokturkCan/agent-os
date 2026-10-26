#!/usr/bin/env python3
"""Verify vendored skills against scripts/runtime/skills.lock.json (stdlib only).

    uv run python scripts/verify_skills_lock.py          # exit 1 on any mismatch

Checks every locked file's sha256, that files named in `must_not_exist` are absent (e.g. an excluded network
downloader, hooks, or an activated copy of a dormant skill), and that no locked folder gained an unlisted file.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "scripts" / "runtime" / "skills.lock.json"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(repo: Path = REPO, lock_path: Path | None = None) -> list[str]:
    lock = json.loads((lock_path or repo / "scripts" / "runtime" / "skills.lock.json").read_text())
    errors: list[str] = []
    for name, e in lock.items():
        want = dict(e.get("sha256", {}))
        want.update(e.get("license_file", {}))
        for rel, digest in want.items():
            p = repo / rel
            if not p.is_file():
                errors.append(f"{name}: missing {rel}")
            elif _sha(p) != digest:
                errors.append(f"{name}: hash mismatch {rel}")
        for rel in e.get("must_not_exist", []):
            if (repo / rel).exists():
                errors.append(f"{name}: must not exist: {rel}")
        listed = set(e.get("sha256", {}))
        # a skill folder is two path segments deep under skills/, three under third_party/<name>/skill
        for root in {"/".join(r.split("/")[: 3 if r.startswith("third_party/") else 2]) for r in listed}:
            base = repo / root
            if base.is_dir():
                for f in base.rglob("*"):
                    if f.is_file() and str(f.relative_to(repo)) not in listed:
                        errors.append(f"{name}: unlisted file {f.relative_to(repo)}")
    return errors


def main() -> int:
    errs = verify()
    for e in errs:
        print("FAIL", e)
    print(f"skills lock: {'OK' if not errs else str(len(errs)) + ' problem(s)'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
