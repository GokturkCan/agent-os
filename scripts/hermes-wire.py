#!/usr/bin/env python3
"""Wire Hermes to Agent OS — HUMAN-RUN ONLY. The only agent-stack code that writes ~/.hermes.

  hermes-wire.py plan                         show the exact diff (no writes)
  hermes-wire.py apply --i-approve [--no-disable]
                                              back up, insert keys, verify, auto-restore on failure
  hermes-wire.py rollback                     restore the most recent backup made by `apply`

Change (under the existing top-level `skills:` block of ~/.hermes/config.yaml):
  skills.external_dirs: [~/agent-stack/skills]           required: Hermes loads agent-os-* skills
  skills.disabled: [claude-code, codex, opencode]         recommended: no direct worker launches

Done as a text insertion (not `hermes config set`, which rewrites the file
and drops its trailing comment block). Verification: the new file must parse,
and after removing exactly these two keys it must equal the original.
"""
from __future__ import annotations

import argparse
import difflib
import shutil
import sys
import time
from pathlib import Path

import yaml

CONFIG = Path.home() / ".hermes" / "config.yaml"
BACKUP_GLOB = "config.yaml.backup-before-agentos-*"
EXTERNAL = "~/agent-stack/skills"
DISABLE = ["claude-code", "codex", "opencode"]


def _insertion(disable: bool) -> str:
    lines = ["  external_dirs:", f"    - {EXTERNAL}"]
    if disable:
        lines += ["  disabled:", *[f"    - {n}" for n in DISABLE]]
    return "\n".join(lines) + "\n"


def render(original: str, disable: bool) -> str:
    cfg = yaml.safe_load(original) or {}
    skills = cfg.get("skills")
    if not isinstance(skills, dict):
        raise SystemExit("expected an existing top-level `skills:` mapping; edit manually")
    if "external_dirs" in skills or (disable and "disabled" in skills):
        raise SystemExit("skills.external_dirs/disabled already present; edit manually")
    out, done = [], False
    for line in original.splitlines(keepends=True):
        out.append(line)
        if not done and line.rstrip("\n") == "skills:":
            out.append(_insertion(disable))
            done = True
    if not done:
        raise SystemExit("could not find a line exactly `skills:`; edit manually")
    return "".join(out)


def verify(original: str, new: str, disable: bool) -> None:
    a, b = yaml.safe_load(original), yaml.safe_load(new)
    assert b["skills"]["external_dirs"] == [EXTERNAL]
    if disable:
        assert b["skills"]["disabled"] == DISABLE
        del b["skills"]["disabled"]
    del b["skills"]["external_dirs"]
    assert a == b, "unexpected change outside skills.external_dirs/disabled"
    assert b["memory"]["memory_enabled"] is False


def diff(a: str, b: str) -> str:
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                        str(CONFIG), str(CONFIG) + " (proposed)"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["plan", "apply", "rollback"])
    ap.add_argument("--i-approve", action="store_true")
    ap.add_argument("--no-disable", action="store_true", help="only add external_dirs")
    a = ap.parse_args()
    disable = not a.no_disable

    if a.action == "rollback":
        backups = sorted(CONFIG.parent.glob(BACKUP_GLOB))
        if not backups:
            print("no agentos backup found", file=sys.stderr)
            return 1
        shutil.copy2(backups[-1], CONFIG)
        print(f"restored {backups[-1]} -> {CONFIG}")
        return 0

    original = CONFIG.read_text()
    new = render(original, disable)
    verify(original, new, disable)
    if a.action == "plan":
        print(diff(original, new) or "no change")
        return 0
    if not a.i_approve:
        print("refusing: apply requires --i-approve (human approval)", file=sys.stderr)
        return 2
    backup = CONFIG.with_name(f"config.yaml.backup-before-agentos-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(CONFIG, backup)
    try:
        CONFIG.write_text(new)
        verify(original, CONFIG.read_text(), disable)
    except Exception:
        shutil.copy2(backup, CONFIG)
        print("verification failed; original restored", file=sys.stderr)
        raise
    print(f"applied; backup at {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
