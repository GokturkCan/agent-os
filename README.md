# Personal Agent OS

Local-first, persistent, knowledge-grounded personal AI system.

This repository is the policy, configuration, workflow, and operational
definition layer for the system.

The architecture is intentionally developed incrementally. Components that
have not been validated in the real system remain candidates until benchmarked.

## Current Architecture

This README stays intentionally brief. For the full current architecture
reference — the Hermes/agent-stack/SecondBrain plane breakdown, hardware,
the cognition pipeline (FastGate/Laya, Qwen, Bonsai, frontier escalation),
execution workers, HarnessRouter, optional subsystems (OpenMausBot,
OpenMuse), telemetry/eval schema, the self-improvement loop, and the current
status table — see:

**[`docs/current-architecture.md`](docs/current-architecture.md)**

---

## 1. Architectural Invariants

These are the current system-level rules.

### One Global Control Plane

**Hermes is the single global orchestrator.**

Models, coding agents, research agents, harnesses, routers, tools, and
automation systems operate under Hermes. They do not become competing global
orchestrators.

### Separation of Responsibilities

**Hermes = WHO runs/orchestrates the system.**
**agent-stack = HOW the system operates.**
**SecondBrain = WHAT the system knows.**

This repository (`agent-stack`) is the policy/config/control-plane
repository for that middle layer. It is not a durable knowledge store, and
it does not itself run the system.

- **Hermes** — runtime control plane
- **agent-stack** — policy, configuration, workflows, evaluation definitions
- **SecondBrain** — durable knowledge
- **models** — cognition
- **workers / harnesses** — execution
- **hardware nodes** — compute resources
- **UI clients** — interaction surfaces

No component should silently duplicate another layer's responsibility.

### Durable Knowledge

Canonical durable knowledge belongs in:

`~/SecondBrain`

Hermes session state or worker-specific memory must not silently become a
second canonical knowledge store.

### State Outside Chat

Important operational state must persist outside model context.

Long-running tasks should be resumable, inspectable, and auditable.

### Deterministic Before Probabilistic

Use ordinary code and deterministic checks whenever they can reliably solve a
decision.

Use model reasoning where actual cognition is required.

### Human-Controlled Critical Actions

Models may propose actions.

Hermes controls execution.

High-risk actions such as destructive filesystem operations, credential
changes, permission expansion, external publishing, production deployment,
money spending, and critical policy changes require explicit policy and,
where appropriate, human approval.

### Controlled Self-Improvement

Self-improvement is not unrestricted self-editing.

Target process:

observe (Hermes task telemetry/results/failures)
→ lesson candidate
→ SecondBrain evidence
→ improvement proposal
→ sandbox
→ evaluate
→ independently judge/review
→ canary
→ promote or rollback
→ agent-stack policy/config

This pipeline is not yet implemented as an autonomous self-modifying system.
It is documented here as the intended target; no worker may implement or
bypass it unilaterally.

Permissions, judges, critical routing policy, canonical knowledge, and
self-improvement evaluation rules must not be rewritten directly by any
worker — they require the review gate above.

### Architecture Freeze Principle

A new framework, model, or service is admitted only when it:

1. fills a real missing capability,
2. materially improves the system,
3. does not introduce unnecessary duplicate orchestration,
4. provides more value than operational complexity.

Otherwise it remains on the watchlist.

---

## 2. Main Paths

### Agent OS Policy

`~/agent-stack`

Contains:

- configuration
- policies
- routing definitions
- permissions
- agent and worker definitions
- skills
- workflows
- evaluation definitions
- operational schemas
- audit material

### Durable Knowledge

`~/SecondBrain`

Human-facing interface:

- Obsidian

### Research Runtime

`~/research-workspaces`

Used for experiments, temporary research state, generated artifacts, and
compute jobs.

---

## 3. Current Verified Environment

### Mac mini

Role:

**primary control node**

Verified characteristics:

- Apple Silicon
- 16 GB unified memory
- Hermes installed
- agent-stack present
- Claude Code installed
- Codex installed
- OpenCode installed
- Prime Agent repository present
- Docker installed
- SecondBrain / Obsidian environment present

The Mac should prioritize lightweight persistent control-plane services rather
than heavy model inference.

### Hermes

Verified:

- installed and runnable
- built-in delegation previously smoke-tested
- file / terminal / skills / vision / delegation toolsets available
- native long-term memory intentionally disabled as canonical memory
  (`memory_enabled: false`, `user_profile_enabled: false`) — because
  `~/SecondBrain` is the canonical durable memory, not Hermes' own store.
  Do not introduce Mem0, Honcho, Graphiti, MegaMem, or a new
  memory/vector-DB dependency to fill this gap; SecondBrain is local-first
  plain Markdown today, and that is sufficient until a real capability gap
  is demonstrated.
- checkpoints and approval controls configured

Hermes is currently installed independently from the system Python.

### Claude / Coding Tooling

Verified components include:

- Claude Code
- Codex
- OpenCode
- Prime Agent
- Serena
- Context7
- Playwright
- research-oriented skill packs

Some tooling overlap remains to be normalized later.

### NVIDIA NIM

NVIDIA API connectivity and authentication are working.

Verified:

- DNS works
- HTTPS/TLS works
- `/v1/models` returns HTTP 200
- `moonshotai/kimi-k3` is present in the model catalog

However, Kimi K3 chat inference timed out with no response during testing
(`audit/nvidia-nim-2026-09-23.md`). `moonshotai/kimi-k3` is currently
**experimental** and must not be treated as reliable.

Separately, `deepseek-ai/deepseek-v4.1-flash` on the same provider, run
through DeepSeek Harness, passed a 20-step autonomous repo-debugging
benchmark (8/8 final suite, 5/5 repeated stability, zero state loss —
`audit/nvidia-nim-2026-09-24.md`). This is **ADOPTED** as a
background/escalation coding specialist (see §6), not as a latency-sensitive
interactive primary backend and not as a second global orchestrator. The
benchmark ran vanilla — no Hermes orchestration, MCP, subagents, skills,
repo RAG, or external verifier — so it validates the model+harness+provider
combination in isolation, not its behavior inside the full Agent OS stack.

---

## 4. Hardware Model

### Mac mini

Intended responsibilities:

- Hermes
- agent-stack
- knowledge services
- lightweight databases
- scheduling
- gateways
- telemetry
- lightweight routing / classification
- optional lightweight local inference

### MSI Ubuntu Laptop

Intended role:

**dynamic compute node**

Candidate workloads:

- local LLM inference
- CUDA / ML
- ROS 2
- Gazebo
- Nav2 / SLAM
- MuJoCo / RL
- computer vision
- VLA experiments
- containerized development workloads

The exact local inference stack is not yet frozen.

### Future RTX 3080 Node

Hardware exists/planned for a future dedicated compute node.

Its final role will be decided after the current Mac + MSI architecture is
validated.

---

## 5. Cognition Architecture

The system is expected to use multiple cognition tiers rather than one model
for every task.

Current conceptual hierarchy:

1. deterministic rules / code
2. fast typed decision layer
3. normal local reasoning
4. stronger local or cloud reasoning
5. frontier specialist models

Exact model assignments remain benchmark-dependent.

### Current Candidates

Under evaluation:

- Laya-MLX for fast typed decisions
- Qwen3.6-35B-A3B for primary local reasoning
- FreeToken as an initial Qwen runtime candidate
- llama.cpp as a fallback runtime candidate
- Bonsai 2 as a possible Mac-side fallback
- Qwen3.8 as a stronger local judge / reasoning candidate
- GLM as an alternative deep-reasoning candidate

These are **candidates**, not architectural requirements.

### Adopted Specialist

- **DeepSeek V4.1 Flash (via NVIDIA NIM + DeepSeek Harness)** — ADOPTED as a
  background/escalation coding specialist for hard repo debugging,
  concurrency bugs, long-horizon coding, refactoring, regression repair,
  code verification, and background engineering. Not a primary interactive
  worker; not a second global orchestrator. See `audit/nvidia-nim-2026-09-24.md`.

---

## 6. Execution Workers

Current or planned worker roles include:

- **Claude Code** — architecture, hard debugging/refactor, review/design judgment
- **Codex** — autonomous implementation, multi-file coding, tests/debugging
- **Muse Code** — parallel coding throughput / worktrees / batch work
- **Antigravity** — browser/editor/multimodal/Google-heavy work
- **Prime** — persistent long-running/general workhorse
- **OpenCode** — overflow/utility worker
- **DeepSeek Harness + DeepSeek V4.1 Flash** — strong background/escalation
  coding specialist (NVIDIA NIM). Not a second global orchestrator; not a
  default interactive worker. See `audit/nvidia-nim-2026-09-24.md`.

None of Prime, DeepSeek Harness, AutoResearch, OpenResearch, Qwen, or n8n
become a second global orchestrator — Hermes remains the single control
plane (§1).

Concurrent coding workers should operate in isolated Git worktrees.

The canonical worker execution abstraction is still under evaluation.

Candidates include:

- AI SDK Harnesses
- HarnessRouter / UHP

Recent tools such as OMP, Pi, fx, Amp, Zed, and OpenHarness remain available
for later evaluation but are not current core dependencies.

---

## 7. Knowledge Architecture

Canonical knowledge:

`SecondBrain`

Current canonical layout:

```
~/SecondBrain/
├── inbox/                  # unprocessed drops, staging only
├── .raw/                   # immutable evidence (append-only)
├── wiki/                   # canonical compiled knowledge
│   ├── sources/
│   ├── meta/ledgers/
│   ├── projects/
│   ├── research/
│   ├── concepts/
│   ├── entities/
│   ├── decisions/
│   ├── index.md
│   ├── hot.md
│   ├── log.md
│   └── overview.md
├── .vault-meta/            # transaction/runtime infrastructure
├── .obsidian/
└── .claude-obsidian.json
```

Rules:

- `.raw/` is immutable evidence. It is not canonical knowledge by itself.
- `wiki/` is canonical compiled knowledge.
- `.vault-meta/` is transaction/runtime infrastructure, not agent-writable
  content.
- Workers must NOT directly overwrite canonical `wiki/`. Workers produce
  drafts, evidence, and proposals (into `inbox/` or their own workspace).
- Canonical writes into `wiki/` must go through the review/transaction/judge
  path (see `config/permissions.yaml`).
- `~/Projects/...` remains real code/data/build storage. SecondBrain project
  folders (`wiki/projects/`) contain only project knowledge/state, not the
  project's actual code or build artifacts.

Target properties:

- human-readable
- local-first
- searchable
- linked
- provenance-aware
- selectively writable by agents (draft/evidence only — see rules above)

Current direction:

- Local-first plain Markdown, using Obsidian + `claude-obsidian` + Kepano
  Obsidian skills as the human-facing/tooling layer.
- Controlled agent writeback, gated by review before canonical mutation.
- BM25 / semantic reranking / temporal graph retrieval are future
  **capability-gap-driven** extensions only — not current dependencies, and
  not required for SecondBrain to function today.

No vector database, graph database, or external search service is required
for the current SecondBrain implementation.

---

## 8. Research Architecture

Research functionality will remain under Hermes.

Target capabilities include:

- literature retrieval
- hypothesis generation
- experiment planning
- automated experiment execution
- metric collection
- independent evaluation
- artifact provenance
- durable result writeback

Candidate systems such as OpenResearch, Scientific Agent Skills,
AIRA-style search, and AutoResearch will be integrated only after the core
Agent OS is operational.

---

## 9. Data and Operations

The system will need durable task state, telemetry, artifacts, and event
handling — this is Hermes/agent-stack **operational** state, distinct from
SecondBrain knowledge content, which stays plain Markdown (§7).

### Optional / Future — capability-gap-driven only

Not installed, not required today, and not to be adopted speculatively:

- PostgreSQL
- pgvector
- Redis (Streams or otherwise)
- Qdrant / Chroma / any generic vector DB

These remain candidates for Hermes' own task-state/telemetry needs only, and
only once a real workload demonstrates the need (capability-gap-before-new-
framework). None of them are a substitute for, or a dependency of,
SecondBrain.

Kafka and Kubernetes are not required Agent OS core dependencies.

---

## 10. Skill Policy

Do not install anything speculatively. Skills load progressively, per task —
not stacked hundreds-deep into standing context.

Current decisions:

- **Scientific Agent Skills** — approved future/current research skill
  registry.
- **Last30Days** — approved fresh/community intelligence capability.
- **Superpowers** — coding-process SOP: *how to perform software
  engineering correctly*. Preferably native inside coding harnesses such as
  Claude Code / Codex.
- **Ponytail** — simplicity/anti-overengineering policy: *how simple the
  resulting implementation should remain*. A separate concern from
  Superpowers, not globally forced onto research or creative work.

Superpowers and Ponytail answer different questions (process vs. output
simplicity) and are not interchangeable or stacked as if they were the same
kind of policy.

## 11. MCP Tool Policy

See `config/mcp.yaml` for the canonical, versioned policy skeleton.

Principles:

- Whitelist only.
- Least privilege per role/task.
- Lazy / progressive loading — load a tool when a task needs it.
- Minimum relevant tools per task.

`config/mcp.yaml` distinguishes three states per tool: **desired**
(candidate, not installed), **installed** (present/configured, may not
work), and **validated** (installed and confirmed working). An MCP is never
described as installed or working here without repo evidence (an audit
file, a passing check) confirming it — see `audit/claude-current-state.md`
for the last full inventory pass.

## 12. Current Implementation Priorities

Near-term work:

1. reconcile live configuration with agent-stack
2. establish a reliable Hermes cognition/provider path
3. connect the MSI compute node
4. benchmark local inference
5. benchmark the fast decision layer
6. define the universal task contract
7. define worker lifecycle and execution abstraction
8. connect Hermes directly to SecondBrain
9. implement durable task/state storage
10. add telemetry and evaluation
11. implement resource scheduling
12. add background automation and messaging
13. integrate the research workflow
14. add richer user interfaces
15. enable controlled self-improvement

The order may change when testing reveals new dependencies.

---

## 13. Decision States

Architecture decisions should be classified as:

### VERIFIED

Confirmed in the live system.

### ADOPTED

Tested and selected for production use.

### CANDIDATE

Promising but not yet validated.

### EXPERIMENTAL

Useful for testing but not relied upon.

### REJECTED

Tested and deliberately excluded.

This distinction should be preserved across documentation and configuration.

---

## 14. Documentation Principle

README.md describes the high-level architecture and current direction.

Detailed implementation decisions belong in:

- `docs/` — architecture reference (see `docs/current-architecture.md`)
- `config/`
- `agents/`
- `adapters/`
- `workers/`
- `workflows/`
- `skills/`
- `evals/`
- `state/`
- `scripts/`
- `audit/`
- future architecture decision records

`agents/`, `adapters/`, `workflows/`, `skills/`, `evals/`, `state/`, and
`scripts/` are scaffolded empty directories today (created 2026-09-15, no
content yet) — see `docs/current-architecture.md` §4 for the intended
responsibility of each.

This README is expected to evolve as candidates are benchmarked and decisions
become stable.
