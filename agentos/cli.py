"""agentos — thin CLI over the V1 control-plane utilities.

  agentos health                         control-plane health check
  agentos validate                       validate config/*.yaml
  agentos route <type> [--risk R] [--provider-down P ...] [--msi up|down]
  agentos tool <need>                    which tool serves an info need
  agentos task new|resume|claim|iterate|test|files|fail|checkpoint|handoff|close|list <id> ...
                                         file-backed task state (see skills/agent-os-task)
  agentos launch <worker> <worktree> <prompt> [--profile P]   (prints argv; never runs)
  agentos manifest [--write]             protected-policy manifest check/refresh
  agentos dispatch --task-id ID --type coding --repo PATH --prompt TEXT --verify CMD [--dry-run]
                                         Hermes' execution entry (route -> worktree -> worker -> verify)
  agentos lesson --run-id ID --title T --text L [--evidence E ...]
                                         write a lesson candidate to ~/SecondBrain/inbox/lessons
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config as C
from . import health, router, telemetry
from .permissions import WorkerSession
from .selfimprove import MANIFEST, compute_manifest, verify_manifest
from .taskstate import TaskStore


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agentos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("validate")
    r = sub.add_parser("route")
    r.add_argument("type")
    r.add_argument("--risk", default="low")
    r.add_argument("--provider-down", action="append", default=[])
    r.add_argument("--msi", choices=["up", "down"], default=None)
    r.add_argument("--record", action="store_true", help="append decision to telemetry")
    t = sub.add_parser("tool")
    t.add_argument("need")
    tk = sub.add_parser("task")
    tk.add_argument("action", choices=["new", "show", "resume", "close", "list", "claim", "iterate",
                                       "test", "files", "fail", "checkpoint", "handoff"])
    tk.add_argument("task_id", nargs="?")
    tk.add_argument("--goal")
    tk.add_argument("--acceptance", action="append", default=[])
    tk.add_argument("--task-class", default=None)
    tk.add_argument("--verification", default=None)
    tk.add_argument("--exit-state", default=None)
    tk.add_argument("--worker")
    tk.add_argument("--checkout")
    tk.add_argument("--signal", help="objective progress signal, e.g. '3 failing'")
    tk.add_argument("--note", default="")
    tk.add_argument("--command")
    tk.add_argument("--passed", action="store_true")
    tk.add_argument("--summary", default="")
    tk.add_argument("--file", action="append", default=[])
    tk.add_argument("--hypothesis")
    tk.add_argument("--evidence", default="")
    tk.add_argument("--label")
    tk.add_argument("--to")
    la = sub.add_parser("launch")
    la.add_argument("worker")
    la.add_argument("worktree")
    la.add_argument("prompt")
    la.add_argument("--profile")
    dp = sub.add_parser("dispatch")
    dp.add_argument("--task-id", required=True)
    dp.add_argument("--type", required=True, dest="task_type")
    dp.add_argument("--repo", required=True)
    dp.add_argument("--prompt", required=True)
    dp.add_argument("--verify", required=True, help="single command; exit 0 == acceptance met")
    dp.add_argument("--risk", default="low", choices=["low", "medium", "high"])
    dp.add_argument("--marker", action="append", default=[])
    dp.add_argument("--human-approval-ref")
    dp.add_argument("--profile")
    dp.add_argument("--provider-down", action="append", default=[])
    dp.add_argument("--max-turns", type=int, default=20)
    dp.add_argument("--timeout", type=int, default=1800, help="per-attempt worker deadline (seconds)")
    dp.add_argument("--verify-timeout", type=int, default=600, help="verification deadline (seconds)")
    dp.add_argument("--dry-run", action="store_true")
    mu = sub.add_parser("mutate", help="canonical mutation branch: request -> agentos dispatch (no Hermes loop)")
    mu.add_argument("--text", required=True)
    mu.add_argument("--repo", required=True)
    mu.add_argument("--verify", help="single verification command (default: detected from repo)")
    mu.add_argument("--task-id")
    mu.add_argument("--dry-run", action="store_true")
    it = sub.add_parser("intent", help="deterministic preload decision for a user request")
    it.add_argument("--text", required=True)
    ls = sub.add_parser("lesson")
    ls.add_argument("--run-id", required=True)
    ls.add_argument("--title", required=True)
    ls.add_argument("--text", required=True)
    ls.add_argument("--evidence", action="append", default=[])
    m = sub.add_parser("manifest")
    m.add_argument("--write", action="store_true",
                   help="HUMAN-ONLY: record the reviewed hashes of protected files")
    a = ap.parse_args(argv)

    if a.cmd == "health":
        return health.summarize(health.run_checks())
    cfg = C.load()
    if a.cmd == "validate":
        errs = C.validate(cfg)
        print("\n".join(errs) or "config valid")
        return 1 if errs else 0
    if a.cmd == "route":
        h = {"providers": {p: False for p in a.provider_down}}
        from .resources import probe_node
        msi = (a.msi == "up") if a.msi else probe_node(cfg, "msi")["reachable"]
        h["nodes"] = {"msi": msi, "mac": True}
        d = router.route(cfg, {"type": a.type, "risk": a.risk}, h)
        if a.record:
            telemetry.record(task_type=a.type, route=d.stage, provider=d.provider, worker=d.worker,
                             exit_state=d.exit_state, fallbacks=d.fallbacks, failures=d.failures)
        print(json.dumps(d.to_dict(), indent=2))
        return 0 if d.exit_state is None else 2
    if a.cmd == "tool":
        print(json.dumps(router.route_tool(cfg, a.need), indent=2))
        return 0
    if a.cmd == "task":
        store = TaskStore(cfg)
        if a.action == "list":
            print("\n".join(store.list()))
        elif a.action == "new":
            contract = {"goal": a.goal, "acceptance": a.acceptance}
            if a.task_class:
                contract["task_class"] = a.task_class
            if a.verification:
                contract["verification"] = a.verification
            print(store.create(a.task_id, contract).path)
        elif a.action in ("show", "resume"):
            print(store.get(a.task_id).resume_brief())
        elif a.action == "close":
            store.get(a.task_id).close(a.exit_state, a.note)
        else:
            t = store.get(a.task_id)
            if a.action == "claim":
                t.claim(a.worker, a.checkout)
            elif a.action == "iterate":
                forced = t.iterate(a.signal, a.note)
                if forced:
                    print(f"FORCED EXIT: {forced}")
                    return 3
            elif a.action == "test":
                t.record_test(a.command, a.passed, a.summary)
            elif a.action == "files":
                t.record_files(a.file)
            elif a.action == "fail":
                t.fail_hypothesis(a.hypothesis, a.evidence)
            elif a.action == "checkpoint":
                print(t.checkpoint(a.label))
            elif a.action == "handoff":
                t.handoff(a.to, a.note)
                print(t.path / "handoff.md")
        return 0
    if a.cmd == "launch":
        s = WorkerSession.start(cfg, a.worker, a.profile)
        print(json.dumps(__import__("agentos.workers", fromlist=["x"]).build_launch(
            cfg, s, a.prompt, a.worktree), indent=2))
        return 0
    if a.cmd == "dispatch":
        from .dispatch import dispatch
        res = dispatch(cfg, task_id=a.task_id, task_type=a.task_type, repo=a.repo, prompt=a.prompt,
                       verify=a.verify, risk=a.risk, markers=tuple(a.marker),
                       human_approval_ref=a.human_approval_ref, profile=a.profile,
                       health={"providers": {p: False for p in a.provider_down}},
                       dry_run=a.dry_run, max_turns=a.max_turns, timeout=a.timeout,
                       verify_timeout=a.verify_timeout)
        print(json.dumps(res, indent=2))
        return 0 if res["exit_state"] in (None, "success") else 2
    if a.cmd == "mutate":
        from .intent import decide
        from .mutate import run as run_mutation
        if not decide(cfg, a.text).force:
            print("not a canonical mutation request; use normal Hermes", file=sys.stderr)
            return 2
        res = run_mutation(cfg, a.text, a.repo, verify=a.verify, task_id=a.task_id, dry_run=a.dry_run)
        print(json.dumps(res, indent=2))
        return 0 if res["exit_state"] in (None, "success") else 2
    if a.cmd == "intent":
        from .intent import decide
        d = decide(cfg, a.text)
        print(json.dumps({**d.to_dict(), "hermes_args": ["--skills", d.skill] if d.force else []}))
        return 0
    if a.cmd == "lesson":
        from .knowledge import Vault
        from .selfimprove import write_lesson_candidate
        rec = next((r for r in telemetry.read_all() if r["run_id"] == a.run_id), None)
        if rec is None:
            print(f"unknown run_id {a.run_id} (lessons must cite a recorded run)", file=sys.stderr)
            return 2
        print(write_lesson_candidate(Vault(cfg).root, rec, a.title, a.text, a.evidence))
        return 0
    if a.cmd == "manifest":
        if a.write:
            MANIFEST.write_text(json.dumps({"note": "Reviewed hashes of protected policy/eval files. "
                                            "Refresh only after human review (agentos manifest --write).",
                                            "files": compute_manifest()}, indent=2) + "\n")
            print(f"wrote {MANIFEST}")
            return 0
        drift = verify_manifest()
        print("\n".join(drift) or "protected files match manifest")
        return 1 if drift else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
