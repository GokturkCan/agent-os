---
name: agent-os-task
description: "Agent OS task state: resume, record tests, budgets, handoff."
version: 1.0.0
author: Gokturk Can
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Agent-OS, Task-State, Checkpoint, Resume, Handoff]
    related_skills: [agent-os-orchestrate]
prerequisites:
  commands: [uv]
---

# Agent OS task protocol

## When to Use

- Working inside a task created by `agentos dispatch` or `agentos task new`.
- Resuming after context loss, or taking over a task from another worker.

All commands: `~/agent-stack/bin/agentos ...` (any directory).

## Start or resume

- New task: `~/agent-stack/bin/agentos task new <task-id> --goal "..." --acceptance "..." [--task-class coding] [--verification "pytest -q"]`
- Existing task / after context loss: `~/agent-stack/bin/agentos task resume <task-id>` — trust this brief over memory.

## While working

1. Work only in the checkout named in the brief (your task worktree). Never in another task's checkout.
2. After each meaningful step, record environmental truth:
   - `~/agent-stack/bin/agentos task test <id> --command "pytest -q" [--passed] --summary "3 failed, 12 passed"`
   - `~/agent-stack/bin/agentos task files <id> --file path/a.py --file path/b.py`
   - `~/agent-stack/bin/agentos task fail <id> --hypothesis "..." --evidence "..."`
   - `~/agent-stack/bin/agentos task iterate <id> --signal "3 failing" --note "..."` (exit code 3 = budget forced an exit state; stop)
3. The progress signal must be objective (e.g. "3 failing"). Repeating the same
   signal is not progress; the budget will close the task as `no_progress`.
4. Never retry an approach listed under "Failed hypotheses".
5. Checkpoint before risky steps: `~/agent-stack/bin/agentos task checkpoint <id> --label before-migration`.
6. Hand off: `~/agent-stack/bin/agentos task handoff <id> --to codex --note "why"`; the next worker runs `task claim <id> --worker codex`.

## Finishing

- Close with `~/agent-stack/bin/agentos task close <id> --exit-state <state> --note "..."`, one of: success, blocked, no_progress, unsafe,
  timeout, budget_exhausted, human_handoff.
- Passing deterministic verification is required for `success`.
- Durable lessons go to `~/SecondBrain/inbox/lessons/` only (never `wiki/`).

## Never

- push, add remotes, change credentials/permissions/policy, edit `evals/` or `config/capabilities.yaml`.
- write into `~/SecondBrain/wiki/` or `.raw/` directly.
