# Changelog

Product versions follow [Semantic Versioning](https://semver.org/). The `version:` fields in
`config/*.yaml` are file-format versions and are unrelated to the product version.

Run 1 and Run 2 are engineering milestones that are **both included in V1**. Run 3 is not.

## [1.0.0] — release candidate (prepared 2026-10-14; not tagged, `main` not yet updated)

Evidence for this candidate: full suite 403 passed / 2 skipped (live-only), health 0 FAIL / 3 WARN,
protected manifest and `agentos validate` pass.

### Run 1 — Core Agent OS

- **Hermes boundary.** Hermes stays the sole global orchestrator; Agent OS is the execution, policy
  and task-lifecycle layer. Canonical front door `bin/hermes-agentos`; deterministic intent gate;
  structural mutation path `hermes-agentos` → `agentos mutate` → `agentos dispatch`.
- **Deterministic routing** from `config/routing.yaml` with recorded skip reasons and bounded
  attempt/iteration/wall-clock budgets.
- **Worker dispatch** under capability profiles: strict MCP set, tool allow/deny lists or sandbox,
  rejected bypass flags. Verified live for Claude Code and Codex.
- **Worktree isolation** with a single-owner lease per checkout; the main checkout is never modified.
- **Retry / resume** and **persistent task state** (`state/tasks/`), including checkpoints and
  handoff briefs. Verified with a real failure → retry → resume run.
- **Verifier loop**: deterministic acceptance command, local commit on `agentos/<task>` only.
- **Timeouts**: worker and verifier run in their own process group under a hard deadline
  (SIGTERM → SIGKILL) and consume an attempt. Verified by tests.
- **Telemetry**: append-only TraceRecords and lifecycle events, whitelisted fields, secret-redacted.
- **Human approval boundaries**: high-risk markers stop at `human_handoff`; profile escalation needs an
  operator grant with a human approval reference; self-improvement promotion needs a human.
- **SecondBrain controls**: canonical `wiki/` writes only through a reviewed transaction gate
  (proposal, independent reviewer, human approval reference, compare-and-swap apply). Hermes built-in
  long-term memory stays disabled; SecondBrain is the memory authority.

### Run 2 — Capability Plane

- **CapabilityRegistry** (`config/capability_registry.yaml`, `agentos/capability_registry.py`): typed,
  validated declaration of what workers, tools and skills can do. It keeps registered, installed,
  available, healthy and eligible distinct.
- **Wave A inventory**: 24 providers and 48 capability ids, with adoption status separate from
  install state.
- **Probes** for availability, health and authentication. Tri-state, so unknown is never read as
  unhealthy. Isolated, offline, and never read or print secret values.
- **Deterministic eligibility and ranking** with stable reason codes, ordered fallbacks and a
  blocked/handoff result instead of guessing.
- **Task-type capability mapping** plus explicit and task-contract capability declarations.
  No natural-language inference.
- **CLI**: `agentos capabilities list | show | match | matrix | check`.
- **Telemetry**: `capability_decision` event and a `capabilities` field on trace records.
- **SystemOne typed contract** (`agentos/systemone.py`): contract only, with explicit raw vs calibrated
  confidence semantics. No decision-model backend is integrated.
- **Task-specific MCP handoff**: only MCP servers the capability plan selected for the routed worker
  are added to the launch. Playwright is granted to the coder profile but is present only for tasks
  whose plan selects it (normal coder launch: Context7 + Serena).
- **Real Claude Code acceptance** with capability-aware dispatch (verifier passed, retry/resume compatible).
- **Real Playwright acceptance** (`run2-real-playwright-acceptance-01`): `web.browser_test` → Playwright
  via `extra_mcp`, the browser fetched the local server (`GET / 200`), verifier passed.

### Pre-release hardening

- **Protected manifest fixed across Python versions.** `evals/**` previously matched only directories
  on Python 3.11, so no eval file was hashed (and it reported false drift on 3.13+). Files are now
  discovered explicitly; the manifest covers 39 files and is identical on 3.11 and 3.14.
- **OpenCode fails closed.** Its launch cannot enforce a capability profile, so it is disabled in the
  worker config and registry, refused by `build_launch`, and skipped by the router. It remains
  registered for future use.
- **Worker push guard.** Wildcard deny patterns (`*git*push*`, `*git*remote*`) for Claude Code,
  live-probed against a throwaway remote (the old exact-prefix patterns let five of eight spellings
  through), plus a structural `pre-push` hook injected into every enforced launch.
- **Protected execution policy.** `config/workers.yaml`, `config/mcp.yaml`,
  `config/capability_registry.yaml`, `agentos/workers.py` and `agentos/githooks/**` are now protected.
  The routing risk gate is held by `agentos validate`.
- **Documentation and state reconciliation**: stale branch, remote and Hermes-model statements
  corrected; the nested-dispatch guard documented as cooperative; health reports remote presence as
  information rather than a warning.

### Known non-blocking items

- Hermes has no fallback model configured (health WARN).
- GitHub MCP needs human re-authentication (HTTP 401, health WARN).
- Postman MCP needs authentication (health WARN).
- The nested-dispatch guard remains cooperative (an environment variable), not a capability boundary.
- A real worker timeout → resume acceptance run is still pending (timeouts are verified by tests only).
- CI and static-analysis tooling are deferred; there is no committed secret-scan script.
- OpenCode is disabled until a launch adapter can enforce capability profiles.

### Not in this release (future work)

Run 3 (local intelligence plane): Laya, Ollaya, Jev, Decider and Kev decision backends, confidence
calibration, the ContextGate runtime, and advanced local-model routing (Qwen, Bonsai). Run 4
(research / web plane) is design only.
