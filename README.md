# Agent OS

A local-first control plane that turns one orchestrator (Hermes) and several
coding CLIs (Claude Code, Codex, OpenCode) into a persistent, verifiable,
resumable agent system.

> **Status: V1, private, solo-maintained.** The core control plane is
> implemented and acceptance-tested on one machine. Local-inference, capability
> and research planes are **not** built. See [Status](#project-status) and
> [docs/roadmap.md](docs/roadmap.md).

Hermes decides **who** orchestrates, this repo defines **how** the system
operates, and `SecondBrain` (a separate Markdown vault, not in this repo) holds
**what** it knows. This repository is policy + configuration + a small
deterministic Python control plane. It is not a knowledge store.

## Architecture at a glance

```
user request
    │
    ▼
bin/hermes-agentos            canonical front door
    │  agentos intent         deterministic classifier (config/routing.yaml intent_rules)
    ├── read-only ───────────► normal Hermes chat (skill preloaded)
    └── mutation  ───────────► agentos mutate ─► agentos dispatch
                                   │  route → task state → worktree + lease
                                   │  worker (claude_code | codex | opencode) under a capability profile
                                   │  verifier command → retry / resume / close with exit_state
                                   ▼
                          state/ (tasks, telemetry, events)  — git-ignored runtime state
```

Details: [docs/architecture.md](docs/architecture.md).

## V1 capabilities

| Capability | Status |
|---|---|
| Config as source of truth (`config/*.yaml`, validated) | IMPLEMENTED, VERIFIED |
| Deterministic intent routing; structural mutation branch (Hermes loop bypassed) | IMPLEMENTED, VERIFIED |
| Persistent file-backed task state, checkpoints, handoff, resume | IMPLEMENTED, VERIFIED |
| Per-task git worktree isolation + single-owner lease | IMPLEMENTED, VERIFIED |
| Worker launch under capability profiles (strict MCP, allow/deny tools, sandbox) | IMPLEMENTED; VERIFIED live for Claude Code and Codex. OpenCode is registered but **disabled (fail closed)**: its launch cannot enforce a profile |
| Worker and verifier timeout enforcement (SIGTERM → SIGKILL on process group) | IMPLEMENTED, VERIFIED by tests; real-run timeout/resume acceptance PENDING |
| Verification loop with bounded retry / resume | IMPLEMENTED, VERIFIED (real failure → retry → resume run) |
| Structured telemetry (TraceRecord JSONL) and lifecycle events JSONL, secret-redacted | IMPLEMENTED, VERIFIED |
| Health and config validation | IMPLEMENTED, VERIFIED |
| SecondBrain gate (capture → propose → approve → apply → lint) | IMPLEMENTED, VERIFIED on fixture vaults |
| Self-improvement foundations (protected manifest, proposal gate) | IMPLEMENTED (mechanism only; nothing generates candidates) |
| Run 2 capability plane: registry, probes, deterministic selection, `agentos capabilities` | CLOSED, VERIFIED (tests + real worker and real Playwright acceptance); dispatch applies deterministic task_type mappings and task-specific MCPs; see [docs/capability-plane.md](docs/capability-plane.md) |

## Read-only vs mutation paths

`bin/hermes-agentos "<request>"` asks `agentos intent` to classify the request
deterministically (no model call):

- **Read-only** (explain, review, research, find, …) → normal Hermes (one-shot chat) with
  the `agent-os-orchestrate` skill preloaded.
- **Clear repo mutation** (fix, implement, refactor, …) → `agentos mutate` →
  `agentos dispatch`. Hermes' own write/patch/terminal tools are never reachable
  on this path. Env: `AGENTOS_REPO` (default `$PWD`), `AGENTOS_VERIFY`,
  `AGENTOS_TASK_ID`.

## Quick start

Requirements: macOS or Linux, Python ≥ 3.11, [`uv`](https://docs.astral.sh/uv/),
git. Workers and Hermes are optional for validation but required for real runs
(`claude`, `codex`, `opencode`, `hermes` on `PATH`, each logged in via its own
mechanism).

```bash
uv sync --extra test              # create .venv from uv.lock
./scripts/health-check.sh         # read-only health + config validation
uv run agentos validate           # config cross-reference validation
./scripts/run-evals.sh            # protected-manifest check + full pytest suite

# Inspect a routing / intent decision without running anything:
uv run agentos intent --text "fix the failing test in this repo"
uv run agentos route --help

# Capability plane (read-only): which executor/tool can satisfy a capability, and why
uv run agentos capabilities match code.references
uv run agentos capabilities matrix
uv run agentos capabilities check
```

A real mutation run (spends worker quota; works on a worktree, never on your
checkout directly):

```bash
cd /path/to/your/repo
AGENTOS_VERIFY="python3 -m pytest -q" /path/to/agent-os/bin/hermes-agentos "fix the failing test"
```

Optional live tests that launch real worker CLIs: `AGENTOS_LIVE=1 ./scripts/run-evals.sh`.

## Configuration

All policy is in `config/*.yaml` (models, providers, workers, capabilities,
routing, permissions, MCP, skills, resources, knowledge, promotion, and the
capability_registry — what providers CAN do, distinct from the protected
permission profiles in capabilities.yaml). Credentials
are **never** stored there: files name where a credential lives (an environment
variable, a CLI login, a keychain item). See [.env.example](.env.example) for the
variable names the code reads, and [SECURITY.md](SECURITY.md).

Expected sibling paths (override with env vars, see `.env.example`):
`~/SecondBrain` (durable knowledge), `~/research-workspaces` (research runtime).

## Safety model

- Permissions are enforced by capability boundaries (worker flags, strict MCP
  config, sandbox mode), not only prompts. Bypass flags are rejected.
- Workers never write SecondBrain `wiki/`; writes go through a reviewed
  transaction gate with compare-and-swap.
- Judges (every file under `evals/`), permissions, capability profiles, promotion rules,
  `CLAUDE.md`, the worker/MCP/capability-registry policy and the launch-enforcement code are covered by
  a protected manifest (`evals/protected-manifest.json`); changes need review. `config/routing.yaml`
  is deliberately the tunable surface; its human-approval risk gate is held by `agentos validate`.
- Workers cannot push or rewrite remotes: Claude Code launches carry wildcard deny patterns
  (`*git*push*`, `*git*remote*`, live-probed against a throwaway remote) and every enforced launch
  carries a `pre-push` guard hook. `rm -rf` / `sudo` are prefix-pattern denials only (best-effort).
- Only `claude_code` and `codex` can be launched (`ENFORCED_WORKERS`); any worker whose launch cannot
  enforce a capability profile is refused and skipped by the router.
- Runtime state and raw provider/session evidence are git-ignored.
- Hermes built-in long-term memory stays disabled; SecondBrain is canonical.

## Current limitations

- Single machine (Mac mini). The secondary compute node is not connected.
- No local inference (Laya / Qwen / Bonsai are benchmark candidates only).
- Hermes' primary provider has a low account rate limit (8,000 TPM measured),
  so default-toolset Hermes requests can fail before reaching Agent OS;
  see `audit/hermes-groq-milestone-2026-10-01.md`.
- Real-run timeout/resume acceptance has not been executed (tested with fakes only).
- Telemetry has no TTFT / RAM / VRAM; the worker is one opaque subprocess.
- Research plane is a written contract only. Self-improvement has no autonomous loop.
- OpenCode is disabled until a launch adapter can enforce capability profiles (see `config/workers.yaml`).

## Project status

V1 core: **implemented and acceptance-tested**; latest full suite (Run 2 branch)
`403 passed, 2 skipped` (2 live-only). See [CURRENT_STATE.md](CURRENT_STATE.md).
Run 2 (capability plane) is closed and verified (including real worker and browser acceptance); its branch is pushed to the private `origin` (PR #2 open, not merged). Run 3–4 are future work.

## Roadmap

| Run | Theme | State |
|---|---|---|
| 1 | Core Agent OS | Done (V1); timeout/resume real acceptance pending |
| 2 | Capability plane | Closed, verified (registry, probes, selection, telemetry, SystemOne contract); backends deferred to Run 3 |
| 3 | Local intelligence plane | Not started (candidates only) |
| 4 | Research / web plane | Design only |

Full detail: [docs/roadmap.md](docs/roadmap.md).

## Repository layout

```
agentos/      control-plane library + CLI (config, router, intent, mutate, dispatch, workers, taskstate, worktree, events, telemetry, knowledge, selfimprove, health, capability_registry/probes/policy/cli, systemone)
bin/          agentos (CLI wrapper), hermes-agentos (canonical front door)
config/       canonical YAML policy
docs/         architecture, roadmap, integration, security, design principles
evals/        executable acceptance/regression suite + protected manifest
skills/       Hermes-facing skills (agent-os-orchestrate, agent-os-task)
workflows/    workflow contracts (coding, knowledge ingest, research)
scripts/      health-check, run-evals, hermes-wire
audit/        sanitized milestone / reproducibility notes
state/        runtime state (git-ignored; README only)
```

Long-form principles and hardware notes: [docs/design-principles.md](docs/design-principles.md).
