---
name: agent-os-orchestrate
description: "REQUIRED for all repo code changes. Mutate only via agentos dispatch; never patch/write_file the repo yourself."
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

Load this skill before any repository coding, fix, refactor or review.
Hermes decides the task; Agent OS handles routing, capability-restricted workers,
isolated worktrees, verification, task state, budgets and telemetry.

## MUTATION CONTRACT (hard rule)

For any repository/code mutation (fix, implement, refactor, change), the ONLY legal path is:

Hermes -> agent-os-orchestrate -> `agentos dispatch` -> worker -> verifier

Hermes MAY (read-only): inspect repo state, run `git status`/`git log`/`git diff`,
read files to understand scope, pick the task type and verification command,
and prepare the dispatch request.

Hermes MUST NOT, even when the fix looks trivial:
- use the `patch` tool on the repository;
- use the `write_file` tool on the repository;
- edit repository files in any other way (sed -i, tee, redirects, editors);
- implement the change via terminal commands;
- run the verification command as a substitute for dispatch.

Hermes MUST run `agentos dispatch` with the repo path, task prompt/type and `--verify`.
The worker implements; the verifier decides. The Agent OS result is authoritative
for the execution outcome. If dispatch is unavailable, stop and report; never fall
back to editing the repository yourself.

## Required path

Use `~/agent-stack/bin/agentos dispatch`; never edit the target repository yourself (no `patch`,
`write_file` or shell edits) and never launch `claude`, `codex`, or `opencode` directly. Agent OS selects the worker.
Do not merge, push, add remotes, or change credentials or permissions.
Workers cannot dispatch nested tasks. Preserve the original checkout.

Preview first:

```sh
~/agent-stack/bin/agentos dispatch --task-id TASK --type coding --repo /absolute/repo --prompt "Goal and acceptance; keep tests unchanged" --verify "python3 -m unittest -v" --dry-run
```

Then run the same command without `--dry-run`. Use terminal `background=true,
notify=true`: worker runs can exceed the 180-second foreground limit. Wait for
notification, or inspect once with `agentos task resume TASK`; do not poll in a loop.
`--verify` is one argv command, not shell syntax; use an existing script for
compound checks. Use the user's actual acceptance command.

One task id per unit of work. Re-dispatching the SAME id resumes its worktree
and budgets. Never create a fresh id to evade failed verification or budgets.

## Result handling

- `done`: verification passed; report task/run ids, worker, branch and commit.
  Work stays on `agentos/TASK` for human review. Never merge automatically.
- `retryable`: verification failed, attempts remain; retry the SAME task id with
  a corrected instruction, or ask the user. Do not claim success.
- `stopped`: budget exhausted/no progress; stop and report.
- `not_dispatched`, `refused`, `unsafe`, `human_handoff`: stop and report; human
  approval is required for high-risk work. Do not weaken policy to continue.

For credentials, permissions, publishing, deletion, payments or deployment,
pass `--risk high` or the appropriate `--marker`; only explicit human approval
permits `--human-approval-ref`. Never self-approve.

Other commands: `agentos route coding`, `agentos health`, `agentos task list`,
`agentos task resume TASK`. All use `~/agent-stack/bin/agentos` from any cwd.
SecondBrain canonical writes always require human review; only propose lessons
with `agentos lesson --run-id ID --title "..." --text "..." --evidence "..."`.
