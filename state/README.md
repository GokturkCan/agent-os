# state/ — operational runtime state (not knowledge)

Everything under `state/` except this README is git-ignored: it is live
operational state of the control plane, not policy and not durable knowledge.
Durable outcomes flow to `~/SecondBrain` through the knowledge gate
(`agentos/knowledge.py`).

| Path | Written by | Contents |
|---|---|---|
| `tasks/<task_id>/` | `agentos.taskstate` | long-task state (below) |
| `telemetry/YYYY-MM-DD.jsonl` | `agentos.telemetry` | one TraceRecord per line |
| `runtime/resources.json` | `agentos.resources` | MSI profile state machine |
| `worktrees/` | `agentos.worktree` | default root for task worktrees |
| `approvals/` | operator / human | knowledge approvals, capability grants |
| `knowledge/proposals/` | `agentos.knowledge` | SecondBrain transaction bundles awaiting review |
| `selfimprove/` | `agentos.selfimprove` | improvement candidates and their gate history |

## Long-task state convention

```
state/tasks/<task_id>/
  task.yaml       LoopContract: goal, acceptance (+ optional task_class, verification,
                  budgets, profile, evaluator, escalation, outputs, memory_admission, ...)
  plan.md         accepted plan, stamped with who accepted it and when
  state.json      owner, checkout, iteration, attempts, budgets, progress history,
                  modified_files, tests, failed_hypotheses, checkpoints, handoffs,
                  exit_state
  findings.md     append-only human-readable log
  handoff.md      generated resume brief at each handoff
  checkpoints/    NNNN-<label>.json snapshots of state.json
```

Rules:

- A task has at most one owner; `claim()` by another worker fails until `handoff()`.
- Budgets come from `config/routing.yaml` `budgets` (per task class), overridable
  in the contract. `iterate()` forces `no_progress` when the progress signal is
  unchanged for `no_progress_after` iterations and `budget_exhausted` at
  `max_iterations`; `attempt_failed()` forces `budget_exhausted` at `max_attempts`.
- A closed task (any exit state) refuses further iterations.
- Resume after context loss: `uv run agentos task resume <task_id>` prints the
  full brief from files alone (goal, acceptance, plan, files, last test,
  failed hypotheses, last checkpoint).
