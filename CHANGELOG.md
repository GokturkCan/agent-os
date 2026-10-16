# Changelog

Product versions follow [Semantic Versioning](https://semver.org/). The `version:` fields in
`config/*.yaml` are file-format versions and are unrelated to the product version.

Run 1 and Run 2 are engineering milestones that are **both included in V1**. Run 3 is not.

## [Unreleased]

### Run 3 — R3.3 Mac-side compute-node capability contract (branch `feature/run3-r33-capability-contract`, not merged)

- `config/compute.yaml` (new, **protected**): capability types, declared offerings and human-approved
  authorizations; offerings and authorizations are empty. `config/resources.yaml`: additive
  `nodes.msi.compute` block (`enabled: false`, symbolic `endpoint_ref`/`auth_ref`, declared resources).
- `agentos/compute.py`: configured/installed/healthy/benchmarked/authorized/active ladder; a node's
  advertisement can never authorize. `agentos/compute_jobs.py`: typed job request/result, closed error
  codes, state machine, idempotency ledger, response validation, offline-by-default client protocol.
- `docs/compute-contract.md`: contract and R3.4 handoff. No network client, no MSI integration, no inference.
  SystemOne `null` backend, `fastgate.model: null` and empty activation allowlists are unchanged.

### Run 3 — R3.1 SystemOne router wiring (branch `feature/run3-local-intelligence`, not merged)

- The router's `fastgate` stage now runs a real SystemOne decision step: one typed question
  ("which pre-approved worker?") over options built from the same predicates the cloud stage uses, so
  SystemOne can only narrow, never widen; the human-approval risk gate runs first.
- Backend resolution layer (`systemone.resolve_backend`, `config/routing.yaml` `systemone.backend`):
  `null` (default, always escalates, routing unchanged) and `policy-order` (reference/test backend).
- Additive telemetry fields `systemone_backend`, `systemone_choice`, `systemone_reason`,
  `systemone_escalate`.
- Not included (DESIGN-ONLY / DEFERRED): other decision-model backends (Ollaya, Jev, Decider, Kev),
  confidence calibration, ContextGate. `fastgate.model` stays null.

### Run 3 — R3.2A/R3.2B backend adapter and Laya-MLX candidate (same branch, not merged)

- `agentos/systemone_adapter.py`: backend-neutral adapter layer. Compact redacted payloads, field-by-field
  reply validation (only an offered option and a raw confidence survive), every failure escalates with a
  specific reason code, subprocess runtime with scrubbed offline environment, kill-on-timeout and cool-down.
- `config/systemone.yaml` (new, **protected**): backend definitions (they name executables). `routing.yaml`
  only selects; the default stays `"null"`.
- Laya-MLX as the first backend (`agentos/systemone_workers/laya_worker.py`), installed in an isolated
  git-ignored runtime (`laya-mlx` 0.4.0, `aac6fef/laya-multilingual-mlx` @ `f2b4faf5`, ~906 MiB).
- `agentos systemone smoke|bench` and evidence `audit/laya-mlx-r3.2-2026-10-14.md`: warm p50 ~18 ms,
  valid-choice rate 100%, reproducible across two runs. Laya is **measured (operational only)**; decision
  quality is unmeasured, and it is not a production default.
### Run 3 — R3.2C Phase 1 semantic decision-quality evaluation (same branch, not merged)

- Request formulation: optional, advisory per-option metadata (`option_info`) built only from existing
  config/registry (`agentos/systemone_options.py`) and an opt-in `allow_abstain` (an escalation, never a
  choice). The adapter validates both (allowlist, size cap, ids outside the offered options dropped,
  secret-looking text rejected); the wire format stays protocol v1 and is byte-identical for legacy requests.
- `agentos systemone-eval` + `evals/data/systemone-decisions-v1.yaml`: 66 hand-authored, config-grounded
  labeled cases (61 semantic incl. 9 escalation-gold, 5 policy) and 12 end-to-end routing cases; three
  separate metric layers (decision quality, protocol compliance, end-to-end policy-valid routing),
  reference baselines, an option-order sweep, a description-swap probe and abstention diagnostics.
- Result for Laya-MLX: operationally sound but **no semantic skill demonstrated** (it follows the label
  string; 94.6% of choices unchanged when two workers' descriptions are swapped). Recommendation: keep as a
  baseline only. Evidence: `audit/systemone-eval-r3.2c-phase1-2026-10-14.md`.
- Still pending: R3.2C Phase 2 backend comparison (Decider/Kev/Jev/Ollaya), calibration, ContextGate.

## [1.0.0] — 2026-10-14

Released on `main` via PR #1 (merge commit `91b08aa`). The `v1.0.0` git tag and GitHub Release have not
been created yet.

Evidence for this release: full suite 403 passed / 2 skipped (live-only), health 0 FAIL / 3 WARN,
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
