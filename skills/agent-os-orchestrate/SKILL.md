---
name: agent-os-orchestrate
description: "Dispatch coding work via Agent OS worktrees + verification."
version: 1.0.0
author: Gokturk Can
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Agent-OS, Orchestration, Routing, Worktree, Policy, Coding-Agent]
    related_skills: [agent-os-task]
prerequisites:
  commands: [uv, git]
---

# Agent OS — Hermes execution layer

Hermes decides what should happen and who should do it. `agentos` (in
`~/agent-stack`) is the policy and execution layer that carries it out:
routing, capability-restricted workers, isolated git worktrees, deterministic
verification, file-backed task state and telemetry.

Entry point for every command: `~/agent-stack/bin/agentos` (works from any directory).

## When to Use

- Any code change, bug fix, refactor, test, or code review in a git repository.
- Before choosing a model or worker for a task (ask the router instead of guessing).
- Resuming or checking a long-running task.
- Recording a reusable lesson from a finished run.
- Checking whether the local control plane is healthy.

## Rules

1. Dispatch coding work with `agentos dispatch`. Do not start `claude`, `codex`,
   or `opencode` directly from the terminal: direct launches bypass the worker
   capability profiles, worktree isolation and verification.
2. One task id per unit of work. Re-dispatching the same id resumes the same task
   (same worktree, same budgets); it never starts a parallel attempt.
3. Never merge, push, add remotes, or change credentials/permissions. Report the
   branch and commit to the user; merging is a human decision.
4. `human_handoff` or `unsafe` in a result means stop and ask the user.
5. Budgets are final: when a result says `stopped` (budget_exhausted / no_progress),
   do not loop. Escalate or ask the user.
6. SecondBrain canonical knowledge (`~/SecondBrain/wiki/`) is written only through
   a human-approved review; you may create lesson candidates, never approve them.

## Commands

Health (read-only):

```
~/agent-stack/bin/agentos health
```

Which worker/provider would handle a task type (no side effects):

```
~/agent-stack/bin/agentos route coding
~/agent-stack/bin/agentos tool developer_docs
```

Dispatch a coding task (preview first with `--dry-run`):

```
~/agent-stack/bin/agentos dispatch --task-id fix-login-timeout --type coding \
  --repo ~/Projects/myapp --prompt "Fix the login timeout described in issue notes; keep the API unchanged." \
  --verify "python -m pytest -q" --dry-run
~/agent-stack/bin/agentos dispatch --task-id fix-login-timeout --type coding \
  --repo ~/Projects/myapp --prompt "..." --verify "python -m pytest -q"
```

A real (non `--dry-run`) dispatch can run for many minutes, longer than the
terminal's default foreground timeout. Run it with the terminal tool's
`background=true` and `notify=true`, then read the JSON result when notified
(or check progress with `agentos task resume <task-id>`). Do not poll in a loop.

`--verify` is a single command whose exit code 0 means the acceptance criterion
is met (use a script for compound checks). The JSON result has `status`
(`done` | `retryable` | `stopped` | `not_dispatched` | `refused` | `dry_run`),
`exit_state`, `worker`, `branch`, `commit`, `verify`, and `next_step`. Follow `next_step`.

High-risk work (credentials, permissions, publishing, deletion, deploys, payments):
pass `--risk high` or `--marker <kind>`; the router returns `human_handoff` until the
user gives an approval reference (`--human-approval-ref`).

Inspect or resume a task:

```
~/agent-stack/bin/agentos task list
~/agent-stack/bin/agentos task resume fix-login-timeout
```

Record a lesson candidate from a run (goes to the SecondBrain inbox for review):

```
~/agent-stack/bin/agentos lesson --run-id <run_id from result> --title "Short title" \
  --text "The reusable rule." --evidence "what showed it"
```

## Result handling

| status | Meaning | Do |
|---|---|---|
| done | verification passed, commit on `agentos/<task-id>` | report branch + commit; offer review |
| retryable | verification failed, attempts remain | re-dispatch same task id with a sharper prompt, or ask |
| stopped | budget forced an exit state | stop; summarize `task resume` output to the user |
| not_dispatched | routing blocked or needs human approval | report `trace` / ask for approval |
| refused | nested dispatch from inside a worker | report; do not retry |
