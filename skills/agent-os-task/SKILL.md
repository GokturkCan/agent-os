---
name: agent-os-task
description: Use when running a multi-step or long task under the Agent OS (Hermes-dispatched or manual) — keeps task state in files so work survives context loss, respects loop budgets, and hands off cleanly between workers.
---

# Agent OS task protocol

All commands run from `~/agent-stack` via `uv run agentos ...`.

## Start or resume

- New task: `uv run agentos task new <task-id> --goal "..." --acceptance "..." [--task-class coding] [--verification "pytest -q"]`
- Existing task / after context loss: `uv run agentos task resume <task-id>` — trust this brief over memory.

## While working

1. Work only in the checkout named in the brief (your task worktree). Never in another task's checkout.
2. After each meaningful step, record environmental truth:
   - `uv run agentos task test <id> --command "pytest -q" [--passed] --summary "3 failed, 12 passed"`
   - `uv run agentos task files <id> --file path/a.py --file path/b.py`
   - `uv run agentos task fail <id> --hypothesis "..." --evidence "..."`
   - `uv run agentos task iterate <id> --signal "3 failing" --note "..."` (exit code 3 = budget forced an exit state; stop)
3. The progress signal must be objective (e.g. "3 failing"). Repeating the same
   signal is not progress; the budget will close the task as `no_progress`.
4. Never retry an approach listed under "Failed hypotheses".
5. Checkpoint before risky steps: `uv run agentos task checkpoint <id> --label before-migration`.
6. Hand off: `uv run agentos task handoff <id> --to codex --note "why"`; the next worker runs `task claim <id> --worker codex`.

## Finishing

- Close with `uv run agentos task close <id> --exit-state <state> --note "..."`, one of: success, blocked, no_progress, unsafe,
  timeout, budget_exhausted, human_handoff.
- Passing deterministic verification is required for `success`.
- Durable lessons go to `~/SecondBrain/inbox/lessons/` only (never `wiki/`).

## Never

- push, add remotes, change credentials/permissions/policy, edit `evals/` or `config/capabilities.yaml`.
- write into `~/SecondBrain/wiki/` or `.raw/` directly.
