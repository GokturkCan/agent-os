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
- Time limits are enforced, not advisory: the worker and the verifier each run
  in their own process group under a hard deadline (killed on expiry), and the
  routing budget's wall_clock_minutes caps cumulative execution time per task.
  A timeout consumes one attempt, is persisted in task state (`timeouts`), and
  exhausting the budget on a timeout closes the task as exit_state=timeout.
- Capability plane (Run 2): required capabilities = declared (argument or task
  contract) + the registry's deterministic task_type mapping
  (capability_policy.resolve_required). An unmapped task type with nothing
  declared keeps Run 1 behaviour exactly. A blocked plan stops before execution
  (no guessing); otherwise the eligible worker set narrows the router's chain
  and only MCP servers the plan selected for the routed worker are passed as
  extra_mcp (the profile grant is still enforced at launch). The
  `capability_decision` event is emitted for declared requirements; auto-resolved
  plans are recorded on the result and TraceRecord.
"""
from __future__ import annotations

import os
import math
import shlex
import sys
import time
from pathlib import Path

from . import capability_policy, capability_registry, events, router, telemetry, worktree, workers
from .config import REPO_ROOT, Config
from .permissions import WorkerSession
from .taskstate import TaskError, TaskStore

WORKER_CONTEXT_ENV = "AGENTOS_WORKER_CONTEXT"


def _verify(cmd: str, cwd: Path, timeout: int) -> dict:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop(WORKER_CONTEXT_ENV, None)
    try:
        # argv, no shell: verification is one command; compound checks belong in a script.
        r = workers.run_bounded(shlex.split(cmd), cwd=cwd, env=env, timeout=timeout)
    except (OSError, ValueError) as exc:
        return {"command": cmd, "passed": False, "returncode": None, "summary": f"cannot run: {exc}"}
    if r["timed_out"]:
        return {"command": cmd, "passed": False, "returncode": None, "timed_out": True,
                "summary": f"verification timeout after {timeout}s"}
    tail = (r["stdout"].strip().splitlines() or r["stderr"].strip().splitlines() or [""])[-1]
    return {"command": cmd, "passed": r["returncode"] == 0, "returncode": r["returncode"],
            "summary": tail[:300]}


def _result(**kw) -> dict:
    base = {"task_id": None, "status": None, "exit_state": None, "worker": None, "provider": None,
            "worktree": None, "branch": None, "commit": None, "verify": None, "trace": [],
            "next_step": None}
    base.update(kw)
    return base


def _contract_capabilities(cfg: Config, task_id: str) -> tuple:
    try:
        return tuple(TaskStore(cfg).get(task_id).contract.get("required_capabilities") or ())
    except TaskError:
        return ()


def dispatch(cfg: Config, *, task_id: str, task_type: str, repo: str | Path, prompt: str,
             verify: str, risk: str = "low", markers: tuple = (), human_approval_ref: str | None = None,
             profile: str | None = None, health: dict | None = None, worktree_root: Path | None = None,
             dry_run: bool = False, runner=None, max_turns: int = 20, timeout: int = 1800,
             verify_timeout: int = 600, required_capabilities: tuple = (),
             capability_overrides: dict | None = None) -> dict:
    runner = runner or workers.run
    t_start = time.monotonic()
    events.clear_errors()
    if not dry_run:
        events.emit("task_received", task_id=task_id, status="received", detail=task_type)
    if os.environ.get(WORKER_CONTEXT_ENV):
        events.emit("task_failed", task_id=task_id, exit_state="unsafe", status="refused",
                    detail="nested dispatch refused")
        rec = events.safe_record(task_id=task_id, task_type=task_type, exit_state="unsafe",
                               notes="nested dispatch from inside a worker refused")
        return _result(task_id=task_id, status="refused", exit_state="unsafe",
                       trace=["nested dispatch refused: workers cannot orchestrate"],
                       next_step="report to Hermes", run_id=rec["run_id"])

    event = {"type": task_type, "risk": risk, "markers": list(markers),
             "human_approval_ref": human_approval_ref}
    declared = tuple(required_capabilities) or _contract_capabilities(cfg, task_id)
    try:
        registry = capability_registry.load(cfg)
        caps = capability_policy.resolve_required(registry, declared, task_type)
    except Exception as exc:  # declared caps fail closed below; otherwise Run 1 behaviour
        registry, caps = None, declared
        if not declared:
            print(f"agentos: capability registry unavailable ({type(exc).__name__}); "
                  "task_type mapping skipped", file=sys.stderr)
    cap = {}                     # extra result/record fields; empty == Run 1 shape
    plan = None
    if caps:
        try:
            if registry is None:
                raise capability_registry.RegistryError(["capability registry could not be loaded"])
            plan = capability_policy.plan_for(cfg, caps, task_id=task_id, task_type=task_type,
                                              overrides=capability_overrides, registry=registry)
        except Exception as exc:  # cannot evaluate declared requirements -> fail closed, never guess
            events.emit("task_failed", task_id=task_id, exit_state="blocked", status="not_dispatched",
                        detail=f"capability plane error: {type(exc).__name__}")
            rec = events.safe_record(task_id=task_id, task_type=task_type, exit_state="blocked",
                                     notes=f"capability plane error: {type(exc).__name__}")
            return _result(task_id=task_id, status="not_dispatched", exit_state="blocked",
                           trace=[f"capability plane error: {exc}"[:300]], next_step="report to Hermes",
                           run_id=rec["run_id"])
        cap = {"capabilities": capability_policy.telemetry_payload(plan)}
        if declared and not dry_run:
            capability_policy.emit_decision(plan, task_id)
        if plan.status == "blocked":
            if not dry_run:
                events.emit("task_failed", task_id=task_id, exit_state="blocked", status="not_dispatched",
                            detail="no capability-eligible executor")
            rec = events.safe_record(task_id=task_id, task_type=task_type, exit_state="blocked", **cap,
                                     notes="capability plane: no eligible executor")
            return _result(task_id=task_id, status="not_dispatched", exit_state="blocked",
                           trace=plan.explain(), next_step=plan.next_step, run_id=rec["run_id"], **cap)
        event["eligible_workers"] = plan.eligible_workers
    d = router.route(cfg, event, health)
    extra_mcp = capability_policy.selected_mcp(cfg, registry, plan, d.worker) if plan else ()
    if cap:
        cap["capabilities"]["routed_worker"] = d.worker
        cap["capabilities"]["extra_mcp"] = list(extra_mcp)
    if d.exit_state or not d.worker:
        exit_state = d.exit_state or "blocked"
        events.emit("task_failed", task_id=task_id, exit_state=exit_state, status="not_dispatched",
                    detail="routing stopped before execution")
        rec = events.safe_record(task_id=task_id, task_type=task_type, route=d.stage, exit_state=exit_state,
                               fallbacks=d.fallbacks, failures=d.failures, **cap,
                               notes="routing stopped before execution")
        return _result(task_id=task_id, status="not_dispatched", exit_state=exit_state,
                       trace=d.trace + ([] if d.worker else ["no execution worker for route"]),
                       next_step="human approval required" if exit_state == "human_handoff" else "report to Hermes",
                       run_id=rec["run_id"], **cap)

    repo = Path(repo).resolve()
    if worktree.git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        events.emit("task_failed", task_id=task_id, exit_state="blocked", status="not_dispatched",
                    detail="not a git repository")
        return _result(task_id=task_id, status="not_dispatched", exit_state="blocked",
                       trace=[f"{repo} is not a git repository"])
    session = WorkerSession.start(cfg, d.worker, profile)
    wt_root = Path(worktree_root or os.environ.get("AGENTOS_WORKTREE_ROOT") or REPO_ROOT / "state" / "worktrees")

    if dry_run:
        planned = wt_root / f"{repo.name}-{task_id}"
        launch = workers.build_launch(cfg, session, prompt, repo, max_turns=max_turns, extra_mcp=extra_mcp)
        for f in launch.get("files", {}).values():
            Path(f).unlink(missing_ok=True)
        launch["cwd"] = str(planned)
        return _result(task_id=task_id, status="dry_run", worker=d.worker, provider=d.provider,
                       worktree=str(planned), branch=f"agentos/{task_id}", trace=d.trace,
                       launch_argv=launch["argv"], profile=session.profile,
                       mcp_servers=launch.get("mcp_servers"), **cap)

    store = TaskStore(cfg)
    try:
        task = store.get(task_id)
        st = task.state
        if st["exit_state"]:
            events.emit("task_failed", task_id=task_id, exit_state=st["exit_state"], status="closed",
                        detail="task already closed")
            return _result(task_id=task_id, status="closed", exit_state=st["exit_state"],
                           trace=[f"task already closed: {st['exit_state']}"])
        wt = Path(st["checkout"])
        prompt = f"{task.resume_brief()}\n\n## Instruction\n{prompt}"
    except TaskError:
        contract = {"goal": prompt, "acceptance": [f"`{verify}` exits 0"], "task_class": d.task_class,
                    "verification": verify, "profile": session.profile}
        if declared:
            contract["required_capabilities"] = list(declared)
        task = store.create(task_id, contract)
        task.accept_plan(prompt, accepted_by="hermes")
        wt = worktree.create(repo, task_id, wt_root)

    worktree.acquire(wt, d.worker, task_id)
    run: dict = {}
    v = None
    commit = None
    timed_out = False
    worker_ms = verify_ms = None
    ev = {"task_id": task_id, "worker": d.worker}
    try:
        task.claim(d.worker, checkout=str(wt))
        st0 = task.state
        ev.update(attempt=st0["attempts"] + 1, iteration=st0["iteration"] + 1)
        remaining = task.remaining_seconds()
        if remaining <= 0:
            events.emit("timeout", **ev, timeout_kind="wall_clock", detail="budget exhausted before attempt")
            # Cumulative wall-clock budget already spent: do not start another attempt.
            wall = task.state["budgets"]["wall_clock_minutes"] * 60
            task.record_timeout("worker", wall, "wall_clock")
            task.close("timeout", "wall_clock budget exhausted before attempt")
            exit_state, timed_out = "timeout", True
            status, nxt = "stopped", "escalate or hand to human (wall-clock budget exhausted)"
        else:
            worker_limit, limit_kind = ((timeout, "per_call") if timeout <= remaining
                                        else (remaining, "wall_clock"))
            launch = workers.build_launch(cfg, session, prompt, wt, max_turns=max_turns, extra_mcp=extra_mcp)
            launch["env"] = {WORKER_CONTEXT_ENV: task_id}
            events.emit("worker_started", **ev, status="running")
            started = time.monotonic()
            run = runner(launch, task_id=task_id, task_type=task_type, timeout=math.ceil(worker_limit))
            worker_ms = round((time.monotonic() - started) * 1000, 1)
            events.emit("worker_finished", **ev, duration_ms=worker_ms,
                        status="timeout" if run.get("timed_out")
                        else "ok" if run.get("returncode") == 0 else "failed",
                        detail=f"returncode={run.get('returncode')}")
            changed = [line[3:] for line in worktree.git(wt, "status", "--porcelain").splitlines()]
            if changed:
                task.record_files(changed)
            if run.get("timed_out"):
                # Worker was killed; its partial edits stay in the worktree for the retry.
                timed_out = True
                task.record_timeout("worker", worker_limit, limit_kind)
                events.emit("timeout", **ev, timeout_kind=limit_kind, duration_ms=worker_ms, detail="worker")
                v = {"command": verify, "passed": False, "returncode": None, "timed_out": True,
                     "summary": f"worker timeout after {math.ceil(worker_limit)}s (verification skipped)"}
            else:
                events.emit("verification_started", **ev, status="running")
                v_start = time.monotonic()
                v = _verify(verify, wt, verify_timeout)
                verify_ms = round((time.monotonic() - v_start) * 1000, 1)
                events.emit("verification_finished", **ev, duration_ms=verify_ms,
                            verifier_status="timeout" if v.get("timed_out")
                            else "passed" if v["passed"] else "failed")
                if v.get("timed_out"):
                    timed_out = True
                    task.record_timeout("verify", verify_timeout)
                    events.emit("timeout", **ev, timeout_kind="verify", duration_ms=verify_ms, detail="verification")
            task.record_test(verify, v["passed"], v["summary"])
            task.add_elapsed(time.monotonic() - started)
            ok = v["passed"] and run.get("returncode") == 0
            # Only unsuccessful iterations count toward no-progress / iteration budgets.
            forced = None if ok else task.iterate(
                f"timeout:{'worker' if run.get('timed_out') else 'verify'}" if timed_out
                else f"fail:{v['summary']}", note=f"worker rc={run.get('returncode')}")
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
                    f"{'timeout: ' if timed_out else ''}worker rc={run.get('returncode')}, "
                    f"verify={v['summary']}", exhausted_state="timeout" if timed_out else "budget_exhausted")
                if not exit_state and task.remaining_seconds() <= 0:
                    task.close("timeout", "wall_clock budget exhausted")
                    exit_state = "timeout"
                if exit_state:
                    status, nxt = "stopped", "escalate or hand to human (budget exhausted)"
                else:
                    task.handoff(None, ("worker/verifier timed out" if timed_out else "verification failed")
                                 + "; retry via dispatch with same task_id")
                    status, nxt = "retryable", f"agentos dispatch --task-id {task_id} ... (same task resumes)"
    except Exception as exc:
        events.emit("task_failed", **ev, status="error", detail=type(exc).__name__)
        raise
    finally:
        worktree.release(wt, d.worker)

    wall_ms = round((time.monotonic() - t_start) * 1000, 1)
    attempts = task.state["attempts"]
    if status == "retryable":
        events.emit("retry", **{**ev, "attempt": attempts}, status=status, duration_ms=wall_ms,
                    verifier_status=None if v is None else "skipped" if run.get("timed_out")
                    else "timeout" if v.get("timed_out") else "passed" if v["passed"] else "failed",
                    detail="timeout" if timed_out else "verification failed")
    elif exit_state == "success":
        events.emit("task_completed", **ev, status=status, exit_state=exit_state, duration_ms=wall_ms)
    else:
        events.emit("task_failed", **ev, status=status, exit_state=exit_state, duration_ms=wall_ms)

    rec = events.safe_record(task_id=task_id, task_type=task_type, route=d.stage, worker=d.worker,
                           provider=d.provider, exit_state=exit_state, success=exit_state == "success",
                           fallbacks=d.fallbacks, failures=d.failures,
                           latency_ms=run.get("latency_ms"), artifacts=[commit] if commit else [],
                           retries=task.state["attempts"], **cap,
                           notes="; ".join(n for n in (
                               "timeout" if timed_out else None,
                               f"human_approval_ref={human_approval_ref}" if human_approval_ref else None) if n) or None)
    return _result(task_id=task_id, status=status, exit_state=exit_state, worker=d.worker,
                   provider=d.provider, worktree=str(wt), branch=f"agentos/{task_id}", commit=commit,
                   verify=v, trace=d.trace, next_step=nxt, run_id=rec["run_id"],
                   worker_returncode=run.get("returncode"), timed_out=timed_out,
                   timeouts=task.state.get("timeouts", []),
                   metrics={"task_wall_ms": wall_ms, "worker_ms": worker_ms, "verify_ms": verify_ms,
                            "exit_state": exit_state, "retries": attempts,
                            "unsupported": list(events.UNSUPPORTED)},
                   telemetry_errors=events.errors(), **cap)
