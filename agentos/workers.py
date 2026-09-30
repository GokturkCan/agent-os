"""Build and (optionally) run worker launch commands under a capability profile.

Capability enforcement is structural: allowed tools, sandbox mode and a
strict MCP set are derived from config/capabilities.yaml + config/mcp.yaml;
nothing is granted by prompt text. Forbidden flags are rejected outright.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import telemetry
from .config import Config, expand
from .permissions import PermissionDenied, WorkerSession


def mcp_servers_for(cfg: Config, session: WorkerSession, extra: tuple[str, ...] = ()) -> dict:
    tools = cfg.mcp["tools"]
    names = list(cfg.mcp["exposure"].get(session.profile, [])) + list(extra)
    servers = {}
    for n in names:
        spec = tools[n]
        cap = spec.get("capability")
        if cap and not session.check(cap):
            continue
        if spec.get("health") in ("failing", "needs_auth") or "launch" not in spec:
            continue
        servers[n] = {"command": spec["launch"]["command"], "args": spec["launch"]["args"]}
    return servers


def build_launch(cfg: Config, session: WorkerSession, prompt: str, worktree: Path | str,
                 max_turns: int = 20, extra_mcp: tuple[str, ...] = ()) -> dict:
    spec = cfg.workers["workers"][session.worker]
    if spec.get("status") not in ("available", "configured", "measured"):
        raise PermissionDenied(f"worker {session.worker} status={spec.get('status')}")
    worktree = str(Path(worktree).resolve())
    out = {"worker": session.worker, "profile": session.profile, "cwd": worktree, "files": {}}

    if session.worker == "claude_code":
        tmap = spec["tool_map"]
        allowed = [t for cap, ts in tmap.items() if session.check(cap) for t in ts]
        disallowed = list(spec.get("always_disallowed", []))
        denied_caps = [cap for cap in tmap if cap not in session.grants]
        disallowed += [t for cap in denied_caps for t in tmap[cap]
                       if not (cap == "shell" and "shell_readonly" in session.grants)]
        mcp = {"mcpServers": mcp_servers_for(cfg, session, extra_mcp)}
        allowed += [f"mcp__{n}" for n in mcp["mcpServers"]]
        fd, mcp_file = tempfile.mkstemp(prefix="agentos-mcp-", suffix=".json")
        with open(fd, "w") as fh:
            json.dump(mcp, fh)
        out["files"]["mcp_config"] = mcp_file
        vals = {"prompt": prompt, "max_turns": str(max_turns), "mcp_config_file": mcp_file,
                "allowed_tools": ",".join(allowed), "disallowed_tools": ",".join(disallowed),
                "permission_mode": "acceptEdits" if "fs_write_worktree" in session.grants else "default"}
        out["argv"] = [a.format(**vals) for a in spec["launch"]["argv"]]
        out["mcp_servers"] = sorted(mcp["mcpServers"])
    elif session.worker == "codex":
        sandbox = spec["sandbox_map"].get(session.profile)
        if sandbox is None:
            raise PermissionDenied(f"no codex sandbox for profile {session.profile}")
        vals = {"prompt": prompt, "worktree": worktree, "sandbox": sandbox}
        out["argv"] = [a.format(**vals) for a in spec["launch"]["argv"]]
    elif session.worker == "opencode":
        out["argv"] = [a.format(prompt=prompt) for a in spec["launch"]["argv"]]
    else:
        raise PermissionDenied(f"no launch adapter for {session.worker}")

    for flag in spec.get("never_flags", []):
        if flag in out["argv"]:
            raise PermissionDenied(f"forbidden flag {flag}")
    out["binary_found"] = shutil.which(expand(out["argv"][0]).name) is not None
    return out


def run(launch: dict, task_id: str | None = None, task_type: str = "coding",
        timeout: int = 600) -> dict:
    """Execute a built launch; record measured telemetry (no invented fields)."""
    with telemetry.Timer() as t:
        r = subprocess.run(launch["argv"], cwd=launch["cwd"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL,
                           timeout=timeout)
    result = {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr[-4000:],
              "latency_ms": t.ms}
    fields = dict(task_id=task_id, task_type=task_type, worker=launch["worker"],
                  latency_ms=t.ms, exit_state=None)
    if launch["worker"] == "claude_code":
        try:
            j = json.loads(r.stdout)
            usage = j.get("usage") or {}
            fields.update(tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
                          cache_read_tokens=usage.get("cache_read_input_tokens"),
                          cost_usd=j.get("total_cost_usd"), provider="claude_subscription",
                          notes=f"num_turns={j.get('num_turns')}")
            result["json"] = j
        except (json.JSONDecodeError, TypeError):
            pass
    result["telemetry"] = telemetry.record(**fields)
    for f in launch.get("files", {}).values():
        Path(f).unlink(missing_ok=True)
    return result
