# Changelog

Product versions follow [Semantic Versioning](https://semver.org/). The `version:` fields in
`config/*.yaml` are file-format versions and are unrelated to the product version.

Run 1 and Run 2 are engineering milestones that are **both included in V1**. Run 3 was merged to `main` after V1 (PR #7, `a2c0897`).

## [Unreleased]

### Pre-Run 4 capability rollout (branch `feature/capability-rollout`; protected packet APPROVED and APPLIED 2026-10-25; not yet committed)

- GitHub MCP repaired: user-scope server, macOS-Keychain `headersHelper`, server-side read-only (`X-MCP-Readonly`, 22 read tools); no credential in any repo/config file.
- Installed (isolated, pinned, on demand): MarkItDown 0.1.9 (`state/runtime/markitdown`, hash-locked), Repomix 1.18.1 (`state/runtime/repomix`, `--ignore-scripts`), wrappers `bin/markitdown`, `bin/repomix`.
- Vendored Ponytail v5.3.2 (`16352ac`): `skills/ponytail`, `skills/ponytail-review` only (no plugin wrapper/hooks/ledger/webhook).
- `skills/orchestra-index` + `scripts/gen_orchestra_index.py`: progressive exposure of the 91 Orchestra skills; interactive skill directories untouched.
- Serena v2.1.0 and Context7 4.4.4 pinned in the user MCP config (identical 50-tool set verified).
- Docs: Run 3 merged, remote intentionally public.
- Protected packet (approved by the owner 2026-10-25; record + hashes in `audit/capability-rollout/`): worker-launch pins in `mcp.yaml`; registry corrections; `gh` and macOS `security` denied to dispatched Claude workers; GitHub credential isolation in every dispatched worker launch env (`agentos/workers.py`); `withheld_executables: [gh]`; protected manifest 77 → 78 entries.
- `capability_policy.plan_for` / `capabilities match` now fail closed: a tool the launcher cannot deliver to a worker (GitHub MCP has no launch) or that is withheld (`gh`) is `integration-undeliverable`; GitHub tasks become a human handoff and never fall back to `gh-cli`. Registry integration facts and frozen SystemOne datasets are unchanged.
- Router: `github_structured` → `github_mcp`, `file_to_markdown` → `markitdown`, `repo_packing` → `repomix`.

### Run 3 — final integration (`integration/run3-final`; merged to `main` via PR #7, `a2c0897`; supersedes stacked PRs #3–#6)

- Consolidates R3.1–R3.2H (SystemOne wiring, adapter, evaluations), CN-1 (compute contract), R3.5 (efficiency) and the Open-Jev closure into one reviewable diff against `main`.
  **Protected-file human approval is PENDING** (`docs/run3-protected-approval-packet.md`); the manifest was regenerated mechanically from the integrated tree and is not an approval.
- Invariants unchanged: SystemOne production backend `null`, `tiers.fastgate.model: null`, both `activation.*` allowlists empty, Laya `candidate`, MSI compute disabled, offerings/authorizations empty.
- Compute: MSI enablement/endpoint/auth references moved from the tunable `resources.yaml` into the protected `config/compute.yaml` (`nodes:`); a `compute` block in `resources.yaml` is rejected. Track renamed **CN-1/CN-2** (R3.3 is calibration in the audit record).
- Hermes: `hermes_bridge` ignores archived (`.archive`) skills; the direct-worker disable-list test uses synthetic active skills with a positive precondition, plus archived-skill, partial-disable and YAML-indent regressions.
- Open-Jev closure incorporated selectively: frozen v3 data, research scripts (moved to `scripts/openjev/`, out of the production package), summaries, a fail-closed analysis loader, and a 0.7 MB checksum-verified archive instead of ~17.7 MB of per-decision JSON in history. Shipped Open-Jev NO-GO, Laya NO-GO, hybrid SHADOW-ONLY (advantage over the deterministic prefilter not established: CI crosses 0).
- Minimal offline CI (`.github/workflows/ci.yml`, `docs/ci.md`), stale routing/efficiency documentation corrected.

### Run 3 — CN-1 Mac-side compute-node capability contract (integration branch; supersedes PR #4)

- `config/compute.yaml` (new, **protected**): capability types, declared offerings and human-approved
  authorizations; offerings and authorizations are empty. Node enablement, symbolic
  `endpoint_ref`/`auth_ref` and declared resources live in its protected `nodes:` block (`msi.enabled: false`);
  a `compute` block in the tunable `config/resources.yaml` is rejected by `agentos validate`.
- `agentos/compute.py`: configured/installed/healthy/benchmarked/authorized/active ladder; a node's
  advertisement can never authorize. `agentos/compute_jobs.py`: typed job request/result, closed error
  codes, state machine, idempotency ledger, response validation, offline-by-default client protocol.
- `docs/compute-contract.md`: contract and CN-2 handoff. No network client, no MSI integration, no inference.
  SystemOne `null` backend, `fastgate.model: null` and empty activation allowlists are unchanged.

### Run 3 — R3.5 efficiency patterns (integration branch; supersedes PR #5)

- ContextGate/ToolPruner: failure-signal protection widened (HTTP 4xx/5xx, errno/signal names, OOM/CrashLoop/segfault/certificate/refused/expired ...); ContextGate also protects identifiers
  (hashes, ticket ids, `id=`, ports, version pins, one-line JSON). On new dev/holdout fixtures essential facts lost: 7/7 and 9/9 -> 0 (reduction 80.6/78.8% -> 69.4/68.9%); v1 suites unchanged (35/35, 27/27, 50.7%/46.1%).
- WakeGate: must-wake rule coverage 0/5 and 1/9 -> 5/5 and 9/9 on new fixtures; a model that always says "defer" cannot suppress them. Unnecessary wakes unchanged.
- New `agentos/retrieval_select.py` (BM25 + attribution + citation verifier; embeddings not available). `agentos module-eval --suite retrieval`, `--suite-file`.
- compat adds an additive typed `trace`. Neural paths (Laya) showed no gain. See `docs/efficiency-patterns.md`. Fixtures are model-assisted, not human-reviewed; author knew the holdout.

### Run 3 — R3.1 SystemOne router wiring (integration branch; supersedes PR #3)

- The router's `fastgate` stage now runs a real SystemOne decision step: one typed question
  ("which pre-approved worker?") over options built from the same predicates the cloud stage uses, so
  SystemOne can only narrow, never widen; the human-approval risk gate runs first.
- Backend resolution layer (`systemone.resolve_backend`, `config/routing.yaml` `systemone.backend`):
  `null` (default, always escalates, routing unchanged) and `policy-order` (reference/test backend).
- Additive telemetry fields `systemone_backend`, `systemone_choice`, `systemone_reason`,
  `systemone_escalate`.
- Not included (DESIGN-ONLY / DEFERRED): other decision-model backends (Ollaya, Jev, Decider, Kev),
  confidence calibration, ContextGate. `fastgate.model` stays null.

### Run 3 — R3.2A/R3.2B backend adapter and Laya-MLX candidate (same integration branch)

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
### Run 3 — R3.2C Phase 1 semantic decision-quality evaluation (same integration branch)

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
- Follow-ups R3.2C Phase 2 → R3.2H completed the backend comparison (see `audit/` and `docs/openjev-research.md`): no neural backend is fit for production. Calibration remains design-only.

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
