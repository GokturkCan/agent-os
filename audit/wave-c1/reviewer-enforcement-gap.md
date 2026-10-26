# Wave C1 — is the independent reviewer enforced to differ from the author? (D13, read-only verification)

2026-10-25 · Method: read-only code/config/test search and two pure routing decisions (`agentos route`). Nothing was changed, no worker was launched.

## Verdict

**Not enforced.** "Reviewer differs from the author" exists as prose and as an advisory string, not as behaviour. The only enforced reviewer-independence check in the repository is in the SecondBrain knowledge gate, and it compares caller-supplied names.

## Evidence

| # | Finding | How verified |
|---|---|---|
| G1 | `config/routing.yaml` carries `reviewer_rule: "Reviewer must differ from primary worker (see roles.reviewer)."` on the `coding` class (and, since P1, on `ui_design`). **No code reads `reviewer_rule`.** | `grep` for `reviewer_rule` / `roles` consumers in `agentos/` and `evals/`: no consumer (the only `roles` hits are permission fs-roles and SystemOne option text) |
| G2 | The referenced `roles.reviewer.rule` says "**Prefer** a different model or harness than the primary worker": advisory, and contradicts the "must" wording above | `config/routing.yaml` lines ~142-146 |
| G3 | `dispatch()` has no parameter linking a review to the work it reviews, and `router.route()` takes no author/exclusion input | read of `agentos/dispatch.py` signature and `router.py` |
| G4 | `Task.close()` clears `owner`, so a closed task does not retain which worker authored it; only an explicit `handoff()` appends a from-owner record to `handoffs`. Worker names also appear in telemetry run records, which are not a policy input | `agentos/taskstate.py` (`st["owner"] = None` in handoff and close paths) |
| G5 | Default routing returns the **same harness** for both: `agentos route coding` → `claude_code`; `agentos route review` → `claude_code`; `agentos route ui_design` → `claude_code` (P1 class, claude only until Codex skill delivery is verified) | pure decision output |
| G6 | The one enforced check: `agentos/knowledge.py::approve` raises if `reviewer == proposer`; it compares **strings supplied by the caller**, so it is a process guard, not identity proof | `knowledge.py` lines 140-144 |
| G7 | "Differs" is under-specified: harness (claude_code vs codex), model family, and context are different things. A fresh `claude -p` dispatch has a fresh context but the same model family as the author | reasoning; every dispatch is a new process |
| G8 | Consequence for the Wave C1 pipeline stage 10: unless the caller picks Codex explicitly, the independent review would be Claude reviewing Claude. Codex as reviewer is possible by config (`allowed_profiles` for codex include `reviewer`; the reviewer profile is read-only) but has no MCP under Agent OS launch, so it would review diff + evidence, not live Serena/Context7 | `config/workers.yaml`, registry notes |

## What this means for gate 4

Gate 4 (independent review) cannot be claimed while review independence rests on the orchestrator remembering to choose a different worker. Until enforcement exists the gate harness itself must pin author and reviewer workers explicitly, which tests the reviewer's recall but not the platform guarantee.

## Minimal enforcement design (NOT implemented, NOT a diff; needs its own approval and patch)

1. **Record the author:** at `task.claim(worker)` also append the worker to `state["workers_used"]` (new list; closing does not clear it).
2. **Link the review:** `dispatch(..., reviews: str | None)`; for a task class that declares `requires_reviews: true` (new key on `routing.task_classes.review`), a missing or unknown task id ⇒ `blocked`.
3. **Exclude the author's harness:** `router.route()` accepts `exclude_workers`; dispatch passes the reviewed task's `workers_used`. If no eligible worker remains ⇒ `blocked` with a handoff, never a silent fallback to the author.
4. **Decide the meaning of "differs":** minimum = different `worker`; stronger = different `provider`/model family (needs a provider notion per worker; `claude_subscription` vs `codex_subscription` already exist in routing).
5. **Make the config honest:** turn the `reviewer_rule` strings into the `requires_reviews` key (or delete them), and reconcile "prefer" with "must".
6. **Tests (all deterministic):** same-worker review ⇒ blocked; different worker ⇒ allowed; review without `reviews` ⇒ blocked; author history survives close; existing `review` dry-runs unchanged when no link is required.
Files that would change: `agentos/taskstate.py`, `agentos/router.py`, `agentos/dispatch.py`, `agentos/cli.py` (a flag), `config/routing.yaml`, a new test file under `evals/` (protected, so the manifest refresh applies). Estimated size: small, but `dispatch.py` is the central execution path, so it deserves the same scratch-copy validation and mutation checks used for P1.

## Approval needed to proceed

D13b: authorise preparing the enforcement patch as a separate packet (scratch-validated, unapplied). Nothing in this document changes any policy.
