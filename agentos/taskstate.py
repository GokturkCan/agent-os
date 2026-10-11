"""File-backed long-task state so work survives context loss.

Layout (state/tasks/<task_id>/):
  task.yaml        LoopContract (goal, acceptance, budgets, verification, ...)
  plan.md          accepted plan (with acceptance timestamp)
  state.json       machine state: owner, iteration, progress, files, tests,
                   failed hypotheses, checkpoints, exit_state
  findings.md      human-readable findings log (append-only)
  handoff.md       generated resume/handoff brief
  checkpoints/     numbered JSON snapshots of state.json

Nothing here depends on conversational memory: `resume()` rebuilds the full
working brief from these files alone.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import EXIT_STATES, REPO_ROOT, Config

CONTRACT_REQUIRED = ("goal", "acceptance")
CONTRACT_OPTIONAL = ("task_class", "inputs", "tools", "profile", "context_budget",
                     "budgets", "progress_signal", "verification", "evaluator",
                     "retry_policy", "checkpoint_policy", "escalation", "outputs",
                     "telemetry", "memory_admission", "side_effects")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_root() -> Path:
    return Path(os.environ.get("AGENTOS_STATE_DIR", REPO_ROOT / "state")) / "tasks"


class TaskError(Exception):
    pass


class Task:
    def __init__(self, path: Path):
        self.path = path
        self.id = path.name

    # ------------------------------------------------------------ io
    @property
    def contract(self) -> dict:
        return yaml.safe_load((self.path / "task.yaml").read_text())

    @property
    def state(self) -> dict:
        return json.loads((self.path / "state.json").read_text())

    def _save(self, st: dict):
        tmp = self.path / "state.json.tmp"
        tmp.write_text(json.dumps(st, indent=2, sort_keys=True))
        tmp.replace(self.path / "state.json")   # atomic on POSIX

    def _finding(self, line: str):
        with open(self.path / "findings.md", "a", encoding="utf-8") as fh:
            fh.write(f"- {_now()} {line}\n")

    def _guard_open(self, st: dict):
        if st["exit_state"]:
            raise TaskError(f"task {self.id} is closed ({st['exit_state']})")

    # ------------------------------------------------------ lifecycle
    def accept_plan(self, plan_md: str, accepted_by: str):
        (self.path / "plan.md").write_text(
            f"<!-- accepted_by: {accepted_by} at {_now()} -->\n{plan_md.strip()}\n")
        st = self.state
        st["plan_accepted"] = {"by": accepted_by, "at": _now()}
        self._save(st)
        self._finding(f"plan accepted by {accepted_by}")

    def claim(self, worker: str, checkout: str | None = None):
        st = self.state
        self._guard_open(st)
        if st["owner"] and st["owner"] != worker:
            raise TaskError(f"task {self.id} owned by {st['owner']}; handoff first")
        st["owner"], st["checkout"] = worker, checkout or st.get("checkout")
        self._save(st)

    def iterate(self, progress_signal, note: str = "") -> str | None:
        """Record one loop iteration. Returns a forced exit state when a
        budget trips (no_progress / budget_exhausted), else None."""
        st = self.state
        self._guard_open(st)
        b = st["budgets"]
        st["iteration"] += 1
        hist = st["progress"]
        hist.append({"i": st["iteration"], "signal": progress_signal, "note": note, "at": _now()})
        forced = None
        n = b["no_progress_after"]
        if len(hist) > n and all(h["signal"] == hist[-1]["signal"] for h in hist[-(n + 1):]):
            forced = "no_progress"
        elif st["iteration"] >= b["max_iterations"]:
            forced = "budget_exhausted"
        self._save(st)
        if forced:
            self._finding(f"budget tripped: {forced} at iteration {st['iteration']}")
            self.close(forced, reason=f"forced by budget at iteration {st['iteration']}")
        return forced

    def record_files(self, files: list[str]):
        st = self.state
        st["modified_files"] = sorted(set(st["modified_files"]) | set(files))
        self._save(st)

    def record_test(self, command: str, passed: bool, summary: str):
        st = self.state
        st["tests"].append({"command": command, "passed": passed, "summary": summary, "at": _now()})
        self._save(st)
        self._finding(f"test `{command}`: {'PASS' if passed else 'FAIL'} — {summary}")

    def fail_hypothesis(self, hypothesis: str, evidence: str):
        st = self.state
        st["failed_hypotheses"].append({"hypothesis": hypothesis, "evidence": evidence, "at": _now()})
        self._save(st)
        self._finding(f"rejected hypothesis: {hypothesis} ({evidence})")

    def attempt_failed(self, reason: str, exhausted_state: str = "budget_exhausted") -> str | None:
        st = self.state
        st["attempts"] += 1
        self._save(st)
        if st["attempts"] >= st["budgets"]["max_attempts"]:
            self.close(exhausted_state, reason=f"max_attempts reached: {reason}")
            return exhausted_state
        return None

    # ------------------------------------------------- time limits
    def add_elapsed(self, seconds: float):
        """Accumulate execution time (worker + verification) against wall_clock_minutes."""
        st = self.state
        st["elapsed_seconds"] = round(st.get("elapsed_seconds", 0.0) + max(seconds, 0.0), 3)
        self._save(st)

    def remaining_seconds(self) -> float:
        st = self.state
        return st["budgets"]["wall_clock_minutes"] * 60 - st.get("elapsed_seconds", 0.0)

    def record_timeout(self, stage: str, limit_seconds: float, limit: str = "per_call"):
        """Persist why an attempt was cut short: stage = worker|verify, limit = per_call|wall_clock."""
        st = self.state
        st.setdefault("timeouts", []).append(
            {"stage": stage, "limit": limit, "limit_seconds": round(limit_seconds, 3),
             "iteration": st["iteration"], "at": _now()})
        self._save(st)
        self._finding(f"timeout: {stage} exceeded {limit} limit of {round(limit_seconds)}s")

    def checkpoint(self, label: str) -> Path:
        st = self.state
        cp_dir = self.path / "checkpoints"
        cp_dir.mkdir(exist_ok=True)
        n = len(list(cp_dir.glob("*.json"))) + 1
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", label)[:40]
        cp = cp_dir / f"{n:04d}-{safe}.json"
        cp.write_text(json.dumps({"label": label, "at": _now(), "state": st}, indent=2))
        st["checkpoints"].append(cp.name)
        self._save(st)
        return cp

    def handoff(self, to_worker: str | None, note: str):
        st = self.state
        self._guard_open(st)
        self.checkpoint(f"handoff-{st['owner']}-to-{to_worker}")
        st = self.state
        st["handoffs"].append({"from": st["owner"], "to": to_worker, "note": note, "at": _now()})
        st["owner"] = None
        self._save(st)
        (self.path / "handoff.md").write_text(self.resume_brief())

    def close(self, exit_state: str, reason: str = ""):
        if exit_state not in EXIT_STATES:
            raise TaskError(f"invalid exit state {exit_state}")
        st = self.state
        if st["exit_state"]:
            return
        st["exit_state"], st["closed_at"], st["close_reason"] = exit_state, _now(), reason
        st["owner"] = None
        self._save(st)
        self._finding(f"closed: {exit_state} {reason}")

    # --------------------------------------------------------- resume
    def resume_brief(self) -> str:
        c, st = self.contract, self.state
        plan = (self.path / "plan.md").read_text() if (self.path / "plan.md").exists() else "(no accepted plan)"
        last_test = st["tests"][-1] if st["tests"] else None
        lines = [
            f"# Resume brief — {self.id}",
            f"Goal: {c['goal']}",
            "Acceptance:", *[f"- {a}" for a in c["acceptance"]],
            f"Status: {'closed: ' + st['exit_state'] if st['exit_state'] else 'open'}; "
            f"iteration {st['iteration']}/{st['budgets']['max_iterations']}; "
            f"attempts {st['attempts']}/{st['budgets']['max_attempts']}; owner {st['owner']}",
            f"Checkout: {st.get('checkout')}",
            f"Verification: {c.get('verification')}",
            "## Accepted plan", plan.strip(),
            "## Modified files", *([f"- {f}" for f in st["modified_files"]] or ["- none"]),
            "## Last test",
            f"- `{last_test['command']}` {'PASS' if last_test['passed'] else 'FAIL'}: {last_test['summary']}"
            if last_test else "- none",
            "## Failed hypotheses (do not retry)",
            *([f"- {h['hypothesis']} — {h['evidence']}" for h in st["failed_hypotheses"]] or ["- none"]),
            f"## Last checkpoint: {st['checkpoints'][-1] if st['checkpoints'] else 'none'}",
        ]
        return "\n".join(lines) + "\n"


class TaskStore:
    def __init__(self, cfg: Config, root: Path | None = None):
        self.cfg = cfg
        self.root = Path(root) if root else state_root()

    def create(self, task_id: str, contract: dict) -> Task:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,80}", task_id):
            raise TaskError("task_id must be lowercase slug")
        missing = [k for k in CONTRACT_REQUIRED if not contract.get(k)]
        unknown = set(contract) - set(CONTRACT_REQUIRED) - set(CONTRACT_OPTIONAL)
        if missing or unknown:
            raise TaskError(f"contract missing={missing} unknown={sorted(unknown)}")
        path = self.root / task_id
        if path.exists():
            raise TaskError(f"task {task_id} exists")
        budgets_cfg = self.cfg.routing["budgets"]
        budgets = dict(budgets_cfg["default"])
        budgets.update(budgets_cfg.get(contract.get("task_class", ""), {}))
        budgets.update(contract.get("budgets") or {})
        path.mkdir(parents=True)
        (path / "task.yaml").write_text(yaml.safe_dump(contract, sort_keys=False))
        (path / "findings.md").write_text(f"# Findings — {task_id}\n\n")
        Task(path)._save({
            "task_id": task_id, "created_at": _now(), "owner": None, "checkout": None,
            "iteration": 0, "attempts": 0, "budgets": budgets, "progress": [],
            "modified_files": [], "tests": [], "failed_hypotheses": [], "checkpoints": [],
            "handoffs": [], "plan_accepted": None, "exit_state": None,
            "closed_at": None, "close_reason": None,
        })
        return Task(path)

    def get(self, task_id: str) -> Task:
        path = self.root / task_id
        if not (path / "state.json").exists():
            raise TaskError(f"no task {task_id}")
        return Task(path)

    def list(self) -> list[str]:
        return sorted(p.parent.name for p in self.root.glob("*/state.json"))
