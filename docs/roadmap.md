# Roadmap

Legend: **IMPLEMENTED** code exists · **VERIFIED** exercised by tests or a real run ·
**PARTIAL** some of it works · **DESIGN-ONLY** written down, no code.
Only claims backed by `CURRENT_STATE.md` are marked VERIFIED.

## Run 1 — Core Agent OS (V1)

| Item | State |
|---|---|
| Config as source of truth + validation | IMPLEMENTED, VERIFIED |
| Deterministic routing and intent classification | IMPLEMENTED, VERIFIED |
| Canonical front door + structural mutation branch | IMPLEMENTED, VERIFIED (real mutation acceptance) |
| Task state, worktrees, leases | IMPLEMENTED, VERIFIED |
| Retry / resume | IMPLEMENTED, VERIFIED (real failure → retry → resume) |
| Worker/verifier timeout enforcement | IMPLEMENTED, VERIFIED by tests; **real acceptance PENDING** |
| Verification loop | IMPLEMENTED, VERIFIED |
| Telemetry + lifecycle events | IMPLEMENTED, VERIFIED (no TTFT/RAM/VRAM) |
| Health / config validation | IMPLEMENTED, VERIFIED |
| SecondBrain gated memory | IMPLEMENTED, VERIFIED (fixture vaults) |
| OpenCode worker | DISABLED, fail closed (launch cannot enforce a capability profile; registered for future use) |
| Remaining to close Run 1 | real timeout→resume run (`origin` exists and is intentionally public; pushing is a human step) |

## Run 2 — Capability plane — **CLOSED, VERIFIED** (2026-10-13; merged into `agent-os-v1` via PR #2; included in Agent OS v1.0.0 on `main`)

| Item | State |
|---|---|
| CapabilityRegistry schema, validation, Wave A inventory (R2.1/R2.2/R2.6) | IMPLEMENTED, VERIFIED |
| Availability / health / auth probes (R2.3) | IMPLEMENTED, VERIFIED (local probes); network probes DEFERRED |
| Required capabilities, eligibility, deterministic selection + fallback (R2.4/R2.5) | IMPLEMENTED, VERIFIED |
| Capability telemetry / explanation (R2.7), parity matrix (R2.8), `agentos capabilities` CLI | IMPLEMENTED, VERIFIED |
| Dispatch integration (declared caps + deterministic task_type mapping) | IMPLEMENTED, VERIFIED (tests, dry-runs, real Claude Code worker acceptance) |
| SystemOne/FastGate typed contract (R2.10) | IMPLEMENTED (contract only); backends DEFERRED to Run 3 |
| Plan-selected MCP exposure into worker launch (Playwright task-specific) | IMPLEMENTED, VERIFIED (real browser acceptance: `GET / 200`, verifier passed) |
| ContextGate (per-task context loading policy) | DESIGN-ONLY |

Evidence: 403 passed / 2 skipped (333 at Run 2 closure, before pre-release hardening) (live-only); see [capability-plane.md](capability-plane.md). Not in Run 2: natural-language capability inference, SystemOne backends, calibration, ContextGate (Run 3+).

## Run 3 — Local intelligence plane — **MERGED to `main`** (PR #7, `a2c0897`; no neural backend activated)

| Item | State |
|---|---|
| R3.1 Router/SystemOne wiring (`fastgate` stage asks the configured backend one typed worker question over policy-eligible options) | IMPLEMENTED, VERIFIED by tests (null backend by default; escalation keeps routing identical to v1.0.0, 900/900 differential cases) |
| R3.2A Backend adapter layer (`systemone_adapter`: typed payload/reply validation, scrubbed-environment subprocess runtime (not an OS/network sandbox), timeout kill, cool-down; definitions in protected `config/systemone.yaml`) | IMPLEMENTED, VERIFIED by tests (fail-closed to escalation on every failure mode; mutation-checked) |
| R3.2B Laya-MLX as the first local backend candidate (`agentos systemone smoke|bench`) | IMPLEMENTED; Laya research candidate, status `candidate` (operationally measured: latency, validity, reproducibility); decision quality evaluated in R3.2C Phase 1 (no semantic skill demonstrated); benchmark candidate only, not a default (`systemone.backend` stays `"null"`, `fastgate.model` stays null) |
| R3.2C Phase 1 Semantic decision-quality evaluation (`agentos systemone-eval`: 66 grounded labeled cases, 3 formulations, 3 separate metric layers, baselines, description-swap and abstention probes; authoritative option metadata in the request) | IMPLEMENTED, VERIFIED (reproducible). Result: Laya follows labels, not descriptions; keep as a baseline, do not promote |
| R3.2C Phase 2 – R3.2H Backend comparison and optimisation (Laya, Decider, Kev, Open-Jev, masked variants; independent v2 and v3 frozen sets) | **COMPLETE.** No neural backend is fit for production: shipped Open-Jev NO-GO, Laya NO-GO. The optimised Open-Jev hybrid is a SHADOW-ONLY research candidate (not approved, not started); its advantage over the deterministic prefilter is not statistically established (CI crosses 0). Deterministic policy first. See `docs/openjev-research.md`, `audit/openjev-v3-closure-2026-10-18.md` |
| Deterministic prefilter facts in router eligibility (reviewer ≠ author, failed-worker hand-off, interactive vs background, capability-missing, high-risk-without-approval) | NEXT (no model needed; highest-value follow-up from R3.2H) |
| Confidence calibration, R3.3 (accuracy, ECE, Platt, isotonic, per-workload thresholds) | DESIGN-ONLY (analysis tooling exists; no backend earned calibration) |
| ContextGate runtime | DESIGN-ONLY at runtime; **R3.5: deterministic prototype hardened** (opt-in library + `module-eval`, not wired into Hermes) — `docs/efficiency-patterns.md` |
| Local models (Qwen3.6, Bonsai 2) | DESIGN-ONLY (benchmark candidates, nothing installed) |
| Secondary compute node (resource state machine) | PARTIAL (state machine verified; node not connected). **CN-1 Mac-side compute-node/capability/job contract IMPLEMENTED (mock-tested; `docs/compute-contract.md`)**: no node connected, nothing installed/benchmarked, offerings and authorizations empty. Confidence calibration remains DESIGN-ONLY; this is not a calibration milestone. |

## Run 4 — Research / web plane

| Item | State |
|---|---|
| Research workflow contract (`workflows/research-question.md`, `docs/research-plane.md`) | DESIGN-ONLY |
| Web/research workers, `~/research-workspaces` runtime | DESIGN-ONLY |

## Self-improvement closed loop

Target: observe → lesson → evidence → proposal → sandbox → evaluate → independent review
→ canary → promote/rollback.

| Stage | State |
|---|---|
| Telemetry/events as observation source | IMPLEMENTED, VERIFIED |
| Lesson capture, proposal gate, protected manifest | IMPLEMENTED, VERIFIED (mechanism) |
| Autonomous candidate generation, sandbox eval, canary, rollback automation | DESIGN-ONLY (intentionally absent in V1) |
