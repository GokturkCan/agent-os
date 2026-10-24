"""Build and (optionally) run worker launch commands under a capability profile.

Capability enforcement is structural: allowed tools, sandbox mode and a
strict MCP set are derived from config/capabilities.yaml + config/mcp.yaml;
nothing is granted by prompt text. Forbidden flags are rejected outright.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from . import events, telemetry
from .config import REPO_ROOT, Config, expand
from .permissions import PermissionDenied, WorkerSession


# Workers whose launch adapter below structurally enforces the capability profile (tool
# allow/deny lists or a sandbox, plus a strict MCP set). Any other worker is refused at launch
# and skipped by the router: fail closed instead of running with ambient, unrestricted tools.
ENFORCED_WORKERS = ("claude_code", "codex")

# `pre-push` here always fails. Workers get it through git's env-config (core.hooksPath), so
# every spelling of `git push` they run is stopped regardless of command-pattern matching.
# Trade-off: repo-local hooks do not run for git commands the worker itself issues; dispatch's
# own commit runs without this env. A deliberate `git push --no-verify` / `-c core.hooksPath=`
# is still stopped only by the worker's deny list (Claude) or sandbox (Codex).
GIT_GUARD_HOOKS = REPO_ROOT / "agentos" / "githooks"


def git_push_guard_env(environ=None) -> dict:
    hook = GIT_GUARD_HOOKS / "pre-push"
    if not (hook.is_file() and os.access(hook, os.X_OK)):
        raise PermissionDenied(f"git push guard hook missing or not executable: {hook}")
    environ = os.environ if environ is None else environ
    try:
        n = int(environ.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        n = 0
    return {"GIT_CONFIG_COUNT": str(n + 1), f"GIT_CONFIG_KEY_{n}": "core.hooksPath",
            f"GIT_CONFIG_VALUE_{n}": str(GIT_GUARD_HOOKS)}


# Variables through which a worker shell could reach the user's GitHub identity. Blanked in the worker
# launch env; GH_CONFIG_DIR points `gh` at an empty config so it has no logged-in account. Residual risk
# (documented, tested): `gh auth token` can still fall back to the OS keyring, so the `gh` deny patterns in
# workers.yaml stay the primary control and this is the second layer for API/PR use via a bypassed pattern.
GITHUB_CREDENTIAL_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                          "GITHUB_PERSONAL_ACCESS_TOKEN")


def gh_isolation_env(environ=None) -> dict:
    environ = os.environ if environ is None else environ
    d = Path(environ.get("AGENTOS_STATE_DIR", REPO_ROOT / "state")) / "runtime" / "gh-isolated"
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o700)
    return {"GH_CONFIG_DIR": str(d), **{v: "" for v in GITHUB_CREDENTIAL_VARS}}


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
    if session.worker not in ENFORCED_WORKERS:
        raise PermissionDenied(f"{session.worker}: no launch adapter enforces the capability profile; "
                               "refusing to launch (fail closed)")
    worktree = str(Path(worktree).resolve())
    out = {"worker": session.worker, "profile": session.profile, "cwd": worktree, "files": {},
           "env": {**git_push_guard_env(), **gh_isolation_env()}}

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
    else:
        raise PermissionDenied(f"no launch adapter for {session.worker}")

    for flag in spec.get("never_flags", []):
        if flag in out["argv"]:
            raise PermissionDenied(f"forbidden flag {flag}")
    out["binary_found"] = shutil.which(expand(out["argv"][0]).name) is not None
    return out


def _kill_group(proc: subprocess.Popen, grace: float = 5.0):
    """Terminate the whole process group (worker + its children), then SIGKILL."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_bounded(argv: list[str], *, cwd, env: dict, timeout: float, grace: float = 5.0) -> dict:
    """Run argv in its own session with a hard wall-clock limit.

    On expiry the entire process group is killed (subprocess.run would only kill
    the direct child and can hang on pipes held by grandchildren). Children left
    behind by a normal exit are reaped too, so no attempt leaks processes.
    Returns {returncode, stdout, stderr, timed_out}; returncode is None on timeout.
    """
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    timed_out = False
    try:
        out, err = proc.communicate(timeout=max(timeout, 0))
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc, grace)
        try:
            out, err = proc.communicate(timeout=grace)
        except subprocess.TimeoutExpired:
            out, err = "", ""
    finally:
        _kill_group(proc, 0.1)       # no-op once the group is gone; also covers Ctrl-C
    return {"returncode": None if timed_out else proc.returncode, "stdout": out or "",
            "stderr": err or "", "timed_out": timed_out}


def run(launch: dict, task_id: str | None = None, task_type: str = "coding",
        timeout: int = 600) -> dict:
    """Execute a built launch under a hard deadline; record measured telemetry
    (no invented fields). A timeout returns timed_out=True, returncode=None."""
    try:
        with telemetry.Timer() as t:
            r = run_bounded(launch["argv"], cwd=launch["cwd"], timeout=timeout,
                            env={**os.environ, **launch.get("env", {})})
    finally:
        for f in launch.get("files", {}).values():
            Path(f).unlink(missing_ok=True)
    result = {"returncode": r["returncode"], "stdout": r["stdout"], "stderr": r["stderr"][-4000:],
              "latency_ms": t.ms, "timed_out": r["timed_out"], "timeout_seconds": timeout}
    fields = dict(task_id=task_id, task_type=task_type, worker=launch["worker"],
                  latency_ms=t.ms, exit_state="timeout" if r["timed_out"] else None)
    if launch["worker"] == "claude_code" and not r["timed_out"]:
        try:
            j = json.loads(r["stdout"])
            usage = j.get("usage") or {}
            fields.update(tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
                          cache_read_tokens=usage.get("cache_read_input_tokens"),
                          cost_usd=j.get("total_cost_usd"), provider="claude_subscription",
                          notes=f"num_turns={j.get('num_turns')}")
            result["json"] = j
        except (json.JSONDecodeError, TypeError):
            pass
    if r["timed_out"]:
        fields["notes"] = f"worker killed after {timeout}s"
    result["telemetry"] = events.safe_record(**fields)
    return result
