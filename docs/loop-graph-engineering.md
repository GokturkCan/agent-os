# Loop & Graph Engineering

**Status:** current canonical runtime design methodology. **Last reconciled:** 2026-09-24.

This document does not redesign the Agent OS. It describes how the
architecture already defined in `docs/current-architecture.md` behaves
during long-running or autonomous work — how a single bounded unit of work
(a "loop") is engineered, and when and how loops compose into a graph.

It introduces **no** new agent framework, graph database, vector database,
orchestration framework, memory system, or global control plane. The
canonical triad is unchanged:

**Hermes** = WHO runs and orchestrates the system.
**`~/agent-stack`** = HOW the system operates.
**`~/SecondBrain`** = WHAT the system knows.

## How to read this document

Every contract and field list below is a **scalable policy template, not
mandatory ceremony**. For a trivial, low-risk, short-lived task: use the
smallest useful subset, don't create graph nodes you don't need, don't
require a verifier when deterministic success is obvious, don't checkpoint
when recovery value is negligible, and don't materialize every field of a
contract just because it's listed.

The system stays biased toward:

- the simplest loop that works
- the smallest graph justified by actual dependencies

Do not turn a simple task into an enterprise workflow.

---

## 1. Cumulative Engineering Model

```
Prompt → Context → Harness → Loop → Graph
```

- **Prompt** = instructions for one unit of work.
- **Context** = only the information the model needs for the current task.
- **Harness** = tools, permissions, state, environment, and execution
  scaffolding.
- **Loop** = one bounded agent/work unit repeatedly observing, acting,
  verifying, and stopping.
- **Graph** = coordination among multiple loops, workers, tools, humans, and
  shared state.

Mapped onto the existing architecture:

- **Hermes** = execution/orchestration graph owner.
- **SecondBrain** = durable knowledge substrate.
- **agent-stack** = policy/workflow/eval definitions.
- **workers** = bounded loop executors.

A graph is not required for every task. Default: **one task → one primary
loop.** Introduce graph structure only when justified by one of:

- real dependencies
- parallelizable independent work
- different tools or permissions
- independent verification
- interruption/resume requirements
- shared state across multiple loops
- route-specific cost/authority constraints

If none of these apply, stop at a loop. Do not build a graph "in case."

---

## 2. Loop Engineering

A conceptual **LoopContract** may include:

goal, acceptance criteria, inputs, allowed tools, permission/side-effect
class, context budget, turn budget, time budget, token budget, cost budget,
compute budget, progress signal, deterministic verification, evaluator,
retry policy, checkpoint policy, escalation policy, exit conditions,
output/artifact schema, telemetry requirements, memory admission policy.

**Do not require every field for every task.** A minimal loop may only need:

```
goal
success condition
allowed action
stop condition
result
```

Long-running or high-risk loops should use richer contracts — more of the
fields above get materialized as task value, risk, or duration increase, not
as a fixed ceremony applied uniformly.

---

## 3. Termination / Stopping

Every autonomous loop must have bounded termination behavior. Conceptual end
states:

| End state | Meaning |
|---|---|
| `success` | acceptance criteria met |
| `blocked` | cannot proceed without new input/access |
| `no_progress` | iterating without moving toward the goal |
| `unsafe` | continuing would cross a risk boundary |
| `timeout` | time/turn budget exhausted |
| `budget_exhausted` | cost/token/compute budget exhausted |
| `human_handoff` | decision requires a human |

**No infinite retry loop is allowed.** Retry limits should be proportional
to task value, failure recoverability, side-effect risk, cost, and latency —
a cheap, reversible, high-value retry can afford more attempts than an
expensive, irreversible, low-value one.

---

## 4. Progress Detection

**Repeated activity is not progress.** Each meaningful loop should define a
task-specific progress signal when practical:

- **Coding** — failing tests decrease; build moves closer to passing;
  blockers are eliminated; diff converges toward acceptance criteria.
- **Research** — new evidence found; hypothesis eliminated; metric improved;
  uncertainty reduced.
- **Operations** — queue shrinks; incident severity decreases; required
  resources become available.

After a bounded number of iterations without meaningful progress: change
strategy, or escalate model, or replace worker, or request human input, or
terminate as `blocked`. Endless "try slightly different parameters" behavior
is not permitted.

---

## 5. Environmental Ground Truth

After actions, prefer real environmental evidence whenever available: tests,
exit codes, files, diffs, metrics, API responses, browser state, experiment
outputs, resource state, logs.

**Principle: deterministic validation before probabilistic judgement.**

If `pytest` says 8/8 pass, do not ask an LLM whether the tests probably
passed.

Use LLM judgement for qualities that genuinely require reasoning:
architecture, ambiguity, design quality, research synthesis, relevance,
trade-offs.

---

## 6. Evaluator Independence

Avoid self-evaluation when meaningful independence is practical. A worker
that produced a critical artifact should not be the sole judge of that
artifact.

```
worker
  → deterministic checks
  → independent reviewer/evaluator when needed
```

Examples: Codex implementation → tests → Claude review for critical changes;
Claude implementation → tests → alternate reviewer where useful; hypothesis
generator → independent experimental/evidence evaluation.

This is already the shape of `config/routing.yaml`'s `reviewer` role
("Prefer a different model or harness than the primary worker").

**Do not add a second LLM judge to every trivial task.** Independence is
used where the expected reliability gain justifies the added cost and
complexity — not by default.

---

## 7. Context Hygiene

Prevent context rot. Do not append the entire run history indefinitely.
Preserve primarily: original goal, current plan/state, key evidence, latest
environment observations, unresolved blockers, relevant artifacts, and
decisions that constrain future steps.

For long loops: compact, checkpoint, resume from structured state rather
than replaying the full transcript.

Context should be retrieved task-specifically from SecondBrain — do not
load the whole vault (already stated in `CLAUDE.md`'s Context Loading
section; this document extends the same principle to in-loop history, not
just vault reads).

Expose the minimum relevant tool set to each worker. Tool and skill
availability follows progressive disclosure rather than giant standing
context (already the policy in `docs/current-architecture.md` §13–14 and
`config/mcp.yaml`).

---

## 8. Graph Engineering

A conceptual **GraphNode** contract:

node id, owner/role, LoopContract reference, dependencies, typed inputs,
typed outputs, artifact references, parallelizability, authority/
permissions, idempotency/replay behavior, checkpoint, verifier, on-success
route, on-failure route, on-timeout route.

Again: this is a policy model, not a requirement that every trivial node
instantiate every field.

Graph edges must carry meaningful **data, condition, and/or authority**.
They must not be decorative arrows — an edge that carries nothing a
downstream node reads or a routing decision depends on should not exist.

---

## 9. Idempotency and Side Effects

Any node that performs external side effects should be classified as either
**replay-safe/idempotent** or **explicitly non-replayable**.

| Action | Typical classification |
|---|---|
| read file | usually replay-safe |
| send email | potentially non-replayable |
| deploy production | non-trivial side effect |
| purchase / payment | high-risk non-replayable |

Retry logic must account for this. A retry or recovery path must not
duplicate a side effect that already happened — this is exactly the
"destructive/hard-to-reverse actions require care" boundary already present
in the harness-level safety rules; this section makes it a per-node
property loops and graphs must carry explicitly, not just a general caution.

---

## 10. Fan-Out / Fan-In

Rules:

- parallelize only genuinely independent work
- join only where combined evidence is actually required
- do not duplicate expensive calls without measured value

Multi-agent work is not automatically superior. Use parallelism when it
improves breadth, latency, specialization, or independent verification — not
to create graph complexity merely to increase agent count. This matches
`config/routing.yaml`'s existing principle: "Prefer one worker by default,"
"Add reviewers only when they provide independent value."

---

## 11. Exactly Three Graph Concepts

Distinguish, and do not conflate:

| Graph | Definition |
|---|---|
| **Execution Graph** | Hermes runtime task/control graph |
| **Knowledge Graph** | logical relations inside SecondBrain knowledge |
| **Trace / Provenance Graph** | relationships among runs, routing, tools, artifacts, evaluations, and lessons |

**Do not create a graph database for any of them in V1.**

---

## 12. Execution Graph

Hermes owns execution graph semantics.

```
TASK
  ↓
SPEC
  ↓
PLAN
  ↓
worker loop
  ↓
environment
  ↓
verify
  ├── pass → done
  └── fail → repair/escalate
```

More complex graphs may include decomposition, parallel branches, join,
verifier, human gate — only when justified (§1, §10).

**No new orchestration framework should be introduced just to visualize or
execute this concept.** Use existing Hermes + agent-stack mechanisms unless
a real capability gap appears later.

---

## 13. Knowledge Graph — SecondBrain

Preserve the current canonical SecondBrain architecture exactly as described
in `docs/current-architecture.md` §3: Markdown, `.raw/` evidence, `wiki/`,
source ledger, claim ledger, provenance, transactions.

Do **not** introduce Neo4j, a Postgres requirement, a Redis requirement, a
Qdrant requirement, a Graphiti requirement, or a separate canonical graph
store.

**Make SecondBrain graph-ready as a data model, not by adding
infrastructure.** Use stable IDs and typed relationships where useful.

Candidate relation vocabulary: `based_on`, `evidence_for`, `contradicts`,
`tested_by`, `produced`, `uses`, `depends_on`, `supersedes`, `applies_to`,
`learned_from`, `related_to`.

```
Hypothesis H17
  → based_on    → Paper P04
  → applies_to  → Project P3
  → tested_by   → Experiment E87
  → produced    → Result R12
```

Human-facing links remain normal Obsidian/Markdown links. Any future BM25
index, vector index, entity index, graph index, or temporal index must be
**derived, rebuildable, and non-canonical** from canonical SecondBrain data
— this is the same retrieval-evolution path already stated in
`docs/current-architecture.md` §3.

---

## 14. Trace / Provenance Graph

A conceptual **TraceRecord** so meaningful runs can be connected:

run id, task, route, model, provider, worker, harness, tools, inputs,
retrieved context refs, artifacts, metrics, verifier, result, failure class,
retry/escalation events, resource profile, lesson candidate.

```
RUN-982
  → routed_by      → Laya
  → reasoned_by    → Qwen
  → executed_by    → Codex
  → used           → pytest
  → produced       → commit abc123
  → reviewed_by    → Claude
  → result         → success
  → produced_lesson → LESSON-41
```

This does **not** require a graph database. Structured telemetry/log
records are sufficient for V1 — see `docs/current-architecture.md` §16 for
the telemetry field list this trace record extends.

---

## 15. Karpathy-Style Bounded Experiment Loops

For tasks with objective metrics, use bounded experimental loops: fixed
evaluation harness, constrained editable surface, comparable resource/time
budget, objective metric, keep improvements, revert regressions.

Suitable areas: ML experiments, prompt/routing tuning, local-model serving
benchmarks, retrieval tuning, compiler/performance optimization, resource
scheduling policy tests.

Do not use this pattern when the objective cannot be reduced to a
meaningful metric.

**The candidate under test must not silently modify its evaluator, held-out
data, promotion criteria, security policy, or permissions.**

---

## 16. Reflection / Evaluator-Optimizer Loops

Reflection/evaluator-optimizer patterns are allowed only when: evaluation
criteria are clear, improvement is measurable or meaningfully judgeable, and
the expected quality gain justifies the additional latency/cost.

Do **not** mechanically add self-critique, second-pass rewrite, judge
calls, or reflection to every task.

- simple file rename → no reflection
- critical architecture proposal → evaluator/reviewer may be justified

---

## 17. Self-Improvement

This is the loop/graph-level restatement of the self-improvement pipeline
already defined in `docs/current-architecture.md` §17 — same pipeline, same
prohibitions, framed here as the terminal case of "a run produces a graph
node that proposes changing the graph itself":

```
run
  → telemetry
  → failure/success analysis
  → lesson candidate
  → evidence
  → improvement proposal
  → isolated change
  → held-out eval
  → independent judge
  → canary
  → promote OR rollback
```

Candidate improvements must not silently change: judge definitions, eval
harness, held-out test set, permissions, critical routing safety, secret
handling, promotion criteria, or security policy.

**Human approval remains required for high-risk policy changes.**

---

## 18. Design Bias

- simplest loop that works
- smallest graph justified by dependencies
- explicit state
- explicit authority
- explicit evidence
- explicit stopping conditions
- measurable progress
- deterministic truth before LLM judgement
- independent evaluation where it matters
- no infrastructure before capability gap

**Graph engineering is not the goal. Reliable autonomous work is the
goal.**

---

## Appendix — Compatibility Review (2026-09-24)

A review of `docs/current-architecture.md`, `CLAUDE.md`, `config/*`,
`workflows/`, `evals/`, and `state/` against this methodology found **no
architectural contradiction** requiring a redesign. Findings:

**Already compliant, no action needed:**

- Evaluator independence (§6) — `config/routing.yaml`'s `reviewer` role
  already requires "a different model or harness than the primary worker."
- One-loop-by-default (§1, §10) — `config/routing.yaml` already states
  "Prefer one worker by default. Add reviewers only when they provide
  independent value."
- No mandatory graph/vector DB (§13) — already explicit policy in
  `docs/current-architecture.md` §3 and this document's §13.
- Self-improvement evaluator/permissions immutability (§17) — already
  stated in `docs/current-architecture.md` §17 and `CLAUDE.md`.
- Progressive tool/skill disclosure (§7) — already policy in `config/mcp.yaml`
  and `docs/current-architecture.md` §13–14.
- SecondBrain context loading, not whole-vault loads (§7) — already stated
  in `CLAUDE.md`'s Context Loading section.

**Real gaps found (not fixed in this pass — documentation only):**

- No numeric retry/turn/time/cost budget exists anywhere in
  `config/routing.yaml`'s `escalation` section today — it names escalation
  *actions* (`retry_or_repair`, `escalate_model_or_specialist`, …) but does
  not bound *how many* retries or *how long* before an end state (§3) is
  forced. This is a real, previously-undocumented gap. It is a config change
  (deciding actual numbers), not a documentation one, so it is deferred, not
  applied here.
- No idempotency/replay classification (§9) exists anywhere in current
  config or docs — this document introduces the concept; no existing policy
  contradicts it, but none previously formalized it either.
- `workflows/`, `evals/`, and `state/` remain empty scaffolded directories
  (confirmed 2026-09-24) — telemetry and eval schemas in
  `docs/current-architecture.md` §16 are declared as intended, not
  implemented. This is an honest, already-acknowledged gap, not a new one.

None of the above requires reversing an existing decision; they are
additions to make explicit once `workflows/`, `evals/`, or `state/` gain
real content — left for a future, config-scoped pass.
