# Architecture (V1)

Labels: **IMPLEMENTED** (code exists) · **VERIFIED** (executed tests/evidence) ·
**PARTIAL** · **FUTURE** (design only, *not* implemented).
Frozen long-form design: [current-architecture.md](current-architecture.md);
module-level map: [v1-implementation.md](v1-implementation.md).

## 1. Roles

| Layer | Owns | Lives in |
|---|---|---|
| Hermes | **WHO** orchestrates; the only global orchestrator | `~/.hermes` (outside this repo) |
| Agent OS (this repo) | **HOW** it operates: policy, routing, state, gates | `agentos/`, `config/` |
| SecondBrain | **WHAT** is known: durable Markdown knowledge | `~/SecondBrain` (separate) |
| Workers | Execution only: Claude Code, Codex, OpenCode | external CLIs |

Workers are downstream executors, never competing orchestrators.

## 2. Control flow

1. **Front door** — `bin/hermes-agentos "<request>"`.
2. **Intent** (`agentos/intent.py`, rules in `config/routing.yaml: intent_rules`) —
   deterministic, no model call. Output: JSON decision incl. `force`.
3. **Read-only** (`force=false`) → normal Hermes with the orchestrate skill preloaded.
4. **Mutation** (`force=true`) → `agentos mutate` (`agentos/mutate.py`): derive task id
   and default verifier, then call `dispatch()`. Normal Hermes is never started.
5. **Dispatch** (`agentos/dispatch.py`): route (`router.py`) → open/resume task
   (`taskstate.py`) → create worktree + lease (`worktree.py`) → launch worker
   (`workers.py`) → run verifier → pass: close `success`; fail: retry within budget;
   budget/timeout exhausted: close with an exit state.

Exit states: `success, blocked, no_progress, unsafe, timeout, budget_exhausted, human_handoff`.

## 3. Execution plane

- **Task state** — file-backed under `state/tasks/` (git-ignored). Survives chat context;
  supports checkpoints, handoff, resume with the same task id.
- **Worktrees** — one task → one worktree on branch `agentos/<task_id>` → one lease
  holder. The original checkout is not modified.
- **Capability profiles** (`config/capabilities.yaml`, `workers.yaml`) — Claude Code runs
  with `--strict-mcp-config`, explicit allow/deny tools; Codex with a sandbox mode; bypass
  flags are rejected.
- **Timeouts** — worker and verifier run in their own process group. On expiry the group
  receives SIGTERM, then SIGKILL after a grace period. A timeout consumes one attempt, is
  recorded in task state, and exhausting the budget closes the task as `timeout`.
  *Verified by tests with fake runners; a real timeout→resume run is still pending.*
- **Retry / resume** — a failed verification or retryable worker error leaves the task
  `retryable`; re-running with the same task id reuses the same worktree and accumulated
  state. *Verified in a real run (first run retryable, second run passed).*
- **Budgets** — attempts, iterations, no-progress and wall-clock limits per task class in
  `config/routing.yaml`.

## 4. Telemetry

Two append-only JSONL streams under `state/telemetry/` (git-ignored):

- **TraceRecords** (`telemetry.py`) — one measured record per run.
- **Lifecycle events** (`events.py`) — `task_received, worker_started, worker_finished,
  verification_started, verification_finished, timeout, retry, task_completed, task_failed`,
  plus `capability_decision` (Run 2; only when a task declares required capabilities).
  Whitelisted fields only; strings truncated; secret-looking values redacted; prompts and
  stdout/stderr are never written; `emit()` never raises.

Not collected (the worker is one opaque subprocess): per-command events, TTFT, RAM, VRAM.
They are never estimated.

## 5. SecondBrain boundary

Agent OS never writes `wiki/` directly. `knowledge.py` builds transaction bundles pinned to
pre-state hashes; approval requires a reviewer different from the proposer, the exact
hash and a human approval reference; apply is compare-and-swap with journaled backups.
Raw sources are not canonical knowledge. Verified on fixture vaults only.

## 6. Health, config, evals

`agentos validate` / `agentos health` (read-only) check config structure, cross-references
and wiring. `evals/` is the executable acceptance suite; `evals/protected-manifest.json`
pins hashes of judge/permission/promotion files.

## 7. Self-improvement foundations

`selfimprove.py` + `config/promotion.yaml`: lesson capture, proposal gate, protected
manifest. Proposal → evaluation → review → promotion is enforced as a mechanism; **no
component generates candidates autonomously**.

## 8. Capability plane (Run 2) — IMPLEMENTED

`capability_registry.py` + `config/capability_registry.yaml` (what providers CAN do),
`capability_probes.py` (availability/health/auth, offline), `capability_policy.py`
(deterministic eligibility, ranking, fallbacks, explanation, telemetry payload),
`agentos capabilities` CLI, and an opt-in `dispatch --require-capability` that narrows
the router's worker chain. `systemone.py` is the backend-neutral SystemOne/FastGate
contract only. See [capability-plane.md](capability-plane.md).

## 9. FUTURE — not implemented

These appear in design docs only. Do not assume any exists in code.

- **SystemOne backends** — a fast local first-pass cognition tier (FastGate/local models:
  Laya-MLX, Decider-2B, ...) behind the Run 2 contract, with calibrated confidence (Run 3).
  The router currently skips these tiers with a recorded reason.
- **ContextGate** — policy that decides what context is loaded into a worker/model per
  task (Runs 2–3).
- Research/web plane, MSI compute node integration, autonomous improvement loop (Runs 3–4).
