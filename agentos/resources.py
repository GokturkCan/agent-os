"""Compute-node reachability and explicit MSI resource-profile transitions.

The Mac never depends on the MSI: probing is bounded, non-fatal, and an
unreachable MSI only makes MSI-hosted stages unusable.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .config import REPO_ROOT, Config


def _ssh_alias_configured(alias: str) -> bool:
    cfg = Path.home() / ".ssh" / "config"
    if not cfg.exists():
        return False
    for line in cfg.read_text(errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].lower() == "host" and alias in parts[1:]:
            return True
    return False


def probe_node(cfg: Config, node: str) -> dict:
    """Return {'reachable': bool, 'reason': str}. Env override for tests:
    AGENTOS_NODE_<NAME>=up|down."""
    override = os.environ.get(f"AGENTOS_NODE_{node.upper()}")
    if override in ("up", "down"):
        return {"reachable": override == "up", "reason": f"env override {override}"}
    spec = cfg.resources["nodes"].get(node, {})
    if node == "mac":
        return {"reachable": True, "reason": "local control plane"}
    reach = spec.get("reachability") or {}
    if reach.get("method") != "ssh":
        return {"reachable": False, "reason": "no reachability method"}
    alias = reach.get("ssh_host_alias", node)
    if not _ssh_alias_configured(alias):
        return {"reachable": False, "reason": f"ssh alias '{alias}' not configured"}
    t = int(reach.get("probe_timeout_seconds", 3))
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={t}", alias, "true"],
                           capture_output=True, timeout=t + 2)
        ok = r.returncode == 0
        return {"reachable": ok, "reason": "ssh ok" if ok else f"ssh exit {r.returncode}"}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"reachable": False, "reason": f"ssh probe failed: {type(exc).__name__}"}


class ResourceScheduler:
    """File-backed MSI profile state machine with explicit ordered steps."""

    def __init__(self, cfg: Config, state_file: Path | None = None):
        self.cfg = cfg
        self.state_file = Path(state_file or os.environ.get(
            "AGENTOS_RESOURCE_STATE", REPO_ROOT / "state" / "runtime" / "resources.json"))

    def state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"msi": {"profile": None, "active_workload": None}}

    def _save(self, st: dict):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st, indent=2))

    def plan_transition(self, target: str, node_reachable: bool) -> dict:
        profiles = self.cfg.resources["profiles"]
        if target not in profiles:
            return {"ok": False, "exit_state": "blocked", "reason": f"unknown profile {target}"}
        if not node_reachable:
            return {"ok": False, "exit_state": "blocked",
                    "reason": "target_node_unreachable: MSI unavailable; Mac control plane unaffected"}
        st = self.state()["msi"]
        if st.get("active_workload") and st.get("profile") != target:
            return {"ok": False, "exit_state": "blocked",
                    "reason": f"another_exclusive_profile_active: {st['profile']}"}
        return {"ok": True, "steps": list(self.cfg.resources["transition"]["steps"]),
                "from": st.get("profile"), "to": target}

    def apply_step_log(self, plan: dict, executed_steps: list[str]) -> dict:
        """Verify steps were executed in order with none skipped, then commit
        the profile. Executing steps on the MSI is the caller's job."""
        expected = plan["steps"]
        if executed_steps != expected[: len(executed_steps)]:
            return {"ok": False, "reason": "steps out of order"}
        if executed_steps != expected:
            return {"ok": False, "reason": f"incomplete: stopped after {executed_steps[-1:] or 'start'}"}
        st = self.state()
        st["msi"] = {"profile": self.cfg.resources.get("default_profile"), "active_workload": None,
                     "last_transition": {"to": plan["to"], "steps": executed_steps}}
        self._save(st)
        return {"ok": True}
