"""Single execution entry point for Hermes: `agentos dispatch`.

Hermes decides WHAT and WHO; this function carries it out under policy:

  route -> (risk gate) -> task state -> worktree + lease -> worker under its
  capability profile -> deterministic verification -> local commit on the
  task branch -> release lease -> telemetry -> JSON result for Hermes

Invariants:
- agentos never invokes Hermes and never merges/pushes; the task branch is
  handed back for a human/Hermes-approved merge.
- Worker processes run with AGENTOS_WORKER_CONTEXT set; dispatch refuses to run
  inside that context, so a worker can never become an orchestrator.
- A failed verification consumes one attempt; the task stays open (lease
  released) until the routing budget forces an exit state.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from . import router, telemetry, worktree, workers
from .config import REPO_ROOT, Config
from .permissions import WorkerSession
from .taskstate import TaskError, TaskStore

WORKER_CONTEXT_ENV = "AGENTOS_WORKER_CONTEXT"


def _verify(cmd: str, cwd: Path, timeout: int) -> dict:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop(WORKER_CONTEXT_ENV, None)
    try:
        # argv, no shell: verification is one command; compound checks belong in a script.
        r = subprocess.run(shlex.split(cmd), cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        tail = (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or [""])[-1]
        return {"command": cmd, "passed": r.returncode == 0, "returncode": r.returncode,
                "summary": tail[:300]}
    except subprocess.TimeoutExpired:
        return {"command": cmd, "passed": False, "returncode": None, "summary": "verification timeout"}
    except (OSError, ValueError) as exc:
        return {"command": cmd, "passed": False, "returncode": None, "summary": f"cannot run: {exc}"}


def _result(**kw) -> dict:
    base = {"task_id": None, "status": None, "exit_state": None, "worker": None, "provider": None,
            "worktree": None, "branch": None, "commit": None, "verify": None, "trace": [],
            "next_step": None}
    base.update(kw)
    return base


def dispatch(cfg: Config, *, task_id: str, task_type: str, repo: str | Path, prompt: str,
             verify: str, risk: str = "low", markers: tuple = (), human_approval_ref: str | None = None,
             profile: str | None = None, health: dict | None = None, worktree_root: Path | None = None,
             dry_run: bool = False, runner=None, max_turns: int = 20, timeout: int = 1800,
             verify_timeout: int = 600) -> dict:
    runner = runner or workers.run
    if os.environ.get(WORKER_CONTEXT_ENV):
        rec = telemetry.record(task_id=task_id, task_type=task_type, exit_state="unsafe",
                               notes="nested dispatch from inside a worker refused")
        return _result(task_id=task_id, status="refused", exit_state="unsafe",
                       trace=["nested dispatch refused: workers cannot orchestrate"],
                       next_step="report to Hermes", run_id=rec["run_id"])

    event = {"type": task_type, "risk": risk, "markers": list(markers),
             "human_approval_ref": human_approval_ref}
    d = router.route(cfg, event, health)
    if d.exit_state or not d.worker:
        exit_state = d.exit_state or "blocked"
        rec = telemetry.record(task_id=task_id, task_type=task_type, route=d.stage, exit_state=exit_state,
                               fallbacks=d.fallbacks, failures=d.failures,
                               notes="routing stopped before execution")
        return _result(task_id=task_id, status="not_dispatched", exit_state=exit_state,
                       trace=d.trace + ([] if d.worker else ["no execution worker for route"]),
                       next_step="human approval required" if exit_state == "human_handoff" else "report to Hermes",
                       run_id=rec["run_id"])

    repo = Path(repo).resolve()
    if worktree.git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        return _result(task_id=task_id, status="not_dispatched", exit_state="blocked",
                       trace=[f"{repo} is not a git repository"])
    session = WorkerSession.start(cfg, d.worker, profile)
    wt_root = Path(worktree_root or os.environ.get("AGENTOS_WORKTREE_ROOT") or REPO_ROOT / "state" / "worktrees")

    if dry_run:
        planned = wt_root / f"{repo.name}-{task_id}"
        launch = workers.build_launch(cfg, session, prompt, repo, max_turns=max_turns)
        for f in launch.get("files", {}).values():
            Path(f).unlink(missing_ok=True)
        launch["cwd"] = str(planned)
        return _result(task_id=task_id, status="dry_run", worker=d.worker, provider=d.provider,
                       worktree=str(planned), branch=f"agentos/{task_id}", trace=d.trace,
                       launch_argv=launch["argv"], profile=session.profile)

    store = TaskStore(cfg)
    try:
        task = store.get(task_id)
        st = task.state
        if st["exit_state"]:
            return _result(task_id=task_id, status="closed", exit_state=st["exit_state"],
                           trace=[f"task already closed: {st['exit_state']}"])
        wt = Path(st["checkout"])
        prompt = f"{task.resume_brief()}\n\n## Instruction\n{prompt}"
    except TaskError:
        task = store.create(task_id, {"goal": prompt, "acceptance": [f"`{verify}` exits 0"],
                                      "task_class": d.task_class, "verification": verify,
                                      "profile": session.profile})
        task.accept_plan(prompt, accepted_by="hermes")
        wt = worktree.create(repo, task_id, wt_root)

    worktree.acquire(wt, d.worker, task_id)
    try:
        task.claim(d.worker, checkout=str(wt))
        launch = workers.build_launch(cfg, session, prompt, wt, max_turns=max_turns)
        launch["env"] = {WORKER_CONTEXT_ENV: task_id}
        run = runner(launch, task_id=task_id, task_type=task_type, timeout=timeout)
        changed = [line[3:] for line in worktree.git(wt, "status", "--porcelain").splitlines()]
        if changed:
            task.record_files(changed)
        v = _verify(verify, wt, verify_timeout)
        task.record_test(verify, v["passed"], v["summary"])
        ok = v["passed"] and run.get("returncode") == 0
        # Only unsuccessful iterations count toward no-progress / iteration budgets.
        forced = None if ok else task.iterate(f"fail:{v['summary']}",
                                              note=f"worker rc={run.get('returncode')}")
        commit = None
        if ok:
            if changed:
                worktree.git(wt, "add", "-A")
                worktree.git(wt, "-c", "user.name=agentos", "-c", "user.email=agentos@localhost",
                             "commit", "-qm", f"agentos: {task_id} ({d.worker})")
            commit = worktree.git(wt, "rev-parse", "HEAD")
            task.close("success", f"verified by `{verify}`")
            status, exit_state, nxt = "done", "success", "review branch, then human-approved merge"
        else:
            exit_state = forced or task.attempt_failed(
                f"worker rc={run.get('returncode')}, verify={v['summary']}")
            if exit_state:
                status, nxt = "stopped", "escalate or hand to human (budget exhausted)"
            else:
                task.handoff(None, "verification failed; retry via dispatch with same task_id")
                status, nxt = "retryable", f"agentos dispatch --task-id {task_id} ... (same task resumes)"
    finally:
        worktree.release(wt, d.worker)

    rec = telemetry.record(task_id=task_id, task_type=task_type, route=d.stage, worker=d.worker,
                           provider=d.provider, exit_state=exit_state, success=exit_state == "success",
                           fallbacks=d.fallbacks, failures=d.failures,
                           latency_ms=run.get("latency_ms"), artifacts=[commit] if commit else [],
                           retries=task.state["attempts"],
                           notes=f"human_approval_ref={human_approval_ref}" if human_approval_ref else None)
    return _result(task_id=task_id, status=status, exit_state=exit_state, worker=d.worker,
                   provider=d.provider, worktree=str(wt), branch=f"agentos/{task_id}", commit=commit,
                   verify=v, trace=d.trace, next_step=nxt, run_id=rec["run_id"],
                   worker_returncode=run.get("returncode"))
