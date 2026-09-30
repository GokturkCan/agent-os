"""Read-only bridge to Hermes for integration checks.

Never writes ~/.hermes. Probes run Hermes' own code (its venv python) against
a throwaway HERMES_HOME that contains only the proposed `skills` keys, so the
integration can be verified before the user approves the real config change.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from .config import REPO_ROOT

HERMES_HOME = Path(os.environ.get("AGENTOS_HERMES_HOME_READONLY", Path.home() / ".hermes"))
HERMES_PY = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python"
AGENT_OS_SKILLS = ("agent-os-orchestrate", "agent-os-task")
DIRECT_WORKER_SKILLS = ("claude-code", "codex", "opencode")   # Hermes bundled skills that launch workers directly
SKILLS_DIR = REPO_ROOT / "skills"


def available() -> bool:
    return HERMES_PY.exists()


def live_config() -> dict:
    p = HERMES_HOME / "config.yaml"
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def _expand(entry: str) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(entry)))
    return (p if p.is_absolute() else HERMES_HOME / p).resolve()


def is_wired(cfg: dict | None = None) -> bool:
    """True when the live Hermes config loads ~/agent-stack/skills."""
    skills = (cfg if cfg is not None else live_config()).get("skills") or {}
    return any(_expand(str(e)) == SKILLS_DIR.resolve() for e in (skills.get("external_dirs") or []))


def direct_worker_skills_enabled(cfg: dict | None = None) -> list[str]:
    cfg = cfg if cfg is not None else live_config()
    disabled = set((cfg.get("skills") or {}).get("disabled") or [])
    present = [n for n in DIRECT_WORKER_SKILLS
               if list((HERMES_HOME / "skills").glob(f"*/{n}/SKILL.md"))]
    return [n for n in present if n not in disabled]


_PROBE = r"""
import dataclasses, json, sys
from pathlib import Path
from agent.skill_utils import get_external_skills_dirs
from tools.skills_tool import skills_list, skill_view
from tools.skill_linter import lint_skill
from tools.skills_guard import scan_skill
names = json.loads(sys.argv[1]); root = Path(sys.argv[2]); seeded = json.loads(sys.argv[3])
out = {"external_dirs": [str(p) for p in get_external_skills_dirs()],
       "listed": [s.get("name") for s in json.loads(skills_list()).get("skills", [])],
       "skills": {}}
for n in names:
    v = json.loads(skill_view(n))
    lint = [dataclasses.asdict(f) for f in lint_skill(root / n / "SKILL.md")]
    g = scan_skill(root / n, source="local")
    out["skills"][n] = {"view_ok": bool(v.get("success")), "lint": lint,
                        "guard_verdict": g.verdict, "guard_findings": len(g.findings)}
out["seeded"] = {n: bool(json.loads(skill_view(n)).get("success")) for n in seeded}
print(json.dumps(out))
"""


def sandbox_config(extra_skills_cfg: dict | None = None) -> dict:
    """The only keys the proposed change adds, in an otherwise empty Hermes home."""
    skills = {"external_dirs": [str(SKILLS_DIR)]}
    skills.update(extra_skills_cfg or {})
    return {"skills": skills, "memory": {"memory_enabled": False, "user_profile_enabled": False}}


def probe(hermes_config: dict | None = None, names=AGENT_OS_SKILLS, timeout: int = 60,
          seed_skills: tuple = ()) -> dict:
    """Run Hermes' skill discovery/linter/guard in a throwaway HERMES_HOME.
    `seed_skills` copies those installed Hermes skills into the sandbox so
    their loadability under the given config can be checked."""
    if not available():
        return {"error": f"Hermes venv not found at {HERMES_PY}"}
    with tempfile.TemporaryDirectory(prefix="agentos-hermes-home-") as home:
        (Path(home) / "skills").mkdir()
        for n in seed_skills:
            for src in (HERMES_HOME / "skills").glob(f"*/{n}"):
                shutil.copytree(src, Path(home) / "skills" / src.parent.name / n)
        (Path(home) / "config.yaml").write_text(yaml.safe_dump(hermes_config or sandbox_config()))
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        env.update(HERMES_HOME=home, PYTHONPATH="")
        r = subprocess.run([str(HERMES_PY), "-c", _PROBE, json.dumps(list(names)), str(SKILLS_DIR),
                            json.dumps(list(seed_skills))],
                           cwd=HERMES_HOME / "hermes-agent", env=env, capture_output=True,
                           text=True, timeout=timeout)
    if r.returncode != 0:
        return {"error": r.stderr.strip()[-1500:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def probe_ok(result: dict) -> tuple[bool, str]:
    if "error" in result:
        return False, result["error"][:300]
    problems = []
    for n in AGENT_OS_SKILLS:
        s = result["skills"].get(n, {})
        if n not in result["listed"]:
            problems.append(f"{n} not discovered")
        if not s.get("view_ok"):
            problems.append(f"{n} not loadable")
        if any(f["severity"] == "error" for f in s.get("lint", [])):
            problems.append(f"{n} lint errors")
        if s.get("guard_verdict") != "safe":
            problems.append(f"{n} guard verdict {s.get('guard_verdict')}")
    return (not problems), ("; ".join(problems) or
                            f"discovered+loadable, lint warnings={sum(len(result['skills'][n]['lint']) for n in AGENT_OS_SKILLS)}, guard safe")
