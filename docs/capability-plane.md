# Capability Plane (Run 2)

Status legend: **IMPLEMENTED** code exists · **VERIFIED** exercised by tests or a real run ·
**PARTIAL** some of it works · **DESIGN-ONLY** written down, no code · **DEFERRED** later run.

The capability plane answers, deterministically and with reasons:

1. What capabilities does this task require?
2. Which registered workers/tools/skills can provide them?
3. Which are available, healthy and authenticated right now?
4. Which candidates are eligible, in what order, and why was each selected or rejected?

```
TASK -> required capabilities -> CapabilityRegistry -> probes (availability/health/auth)
     -> hard filters (adoption, host, locality, cost/risk caps, deny) -> eligible executors/tools
     -> deterministic ranking -> selection + fallbacks -> (dispatch) -> telemetry / explanation
```

| Part | Module | State |
|---|---|---|
| Registry schema + validation (R2.1) | `agentos/capability_registry.py`, `config/capability_registry.yaml` | IMPLEMENTED, VERIFIED |
| Wave A inventory (R2.2) | `config/capability_registry.yaml` | IMPLEMENTED (registration); availability per probe |
| Availability / health / auth probes (R2.3) | `agentos/capability_probes.py` | IMPLEMENTED, VERIFIED (local probes); network/service probes DEFERRED |
| Required capabilities (R2.4) | `capability_policy.resolve_required` | IMPLEMENTED, VERIFIED |
| Eligibility / selection / fallback (R2.5) | `capability_policy.plan` | IMPLEMENTED, VERIFIED |
| Cost / locality / latency / host metadata (R2.6) | registry vocabularies | IMPLEMENTED, VERIFIED |
| Telemetry / explainability (R2.7) | `events.py` `capability_decision`, TraceRecord `capabilities` | IMPLEMENTED, VERIFIED |
| Worker/tool parity matrix (R2.8) | `capability_policy.parity_matrix`, `agentos capabilities matrix` | IMPLEMENTED, VERIFIED |
| Tests / acceptance (R2.9) | `evals/test_capability_*.py`, `evals/test_systemone.py` | VERIFIED |
| SystemOne/FastGate contract (R2.10) | `agentos/systemone.py` | IMPLEMENTED (contract only); backends DEFERRED to Run 3 |
| Dispatch integration | `dispatch(...)`: declared caps + `task_types` mapping | IMPLEMENTED, VERIFIED (tests, dry-runs, real worker acceptance) |
| Plan-selected MCP tools in worker launch | `capability_policy.selected_mcp` → `build_launch(extra_mcp=...)` | IMPLEMENTED, VERIFIED (task-specific; profile grant still enforced; real browser acceptance) |
| ContextGate | — | DESIGN-ONLY |

## Closure and live acceptance (2026-10-13)

Run 2 is **CLOSED, VERIFIED**. Full suite: **333 passed, 2 skipped** (live-only); health 0 FAIL.
Requirements come only from explicit/contract declarations and the deterministic `task_types`
mapping; there is no natural-language capability inference.

| Acceptance | Result |
|---|---|
| Real capability-aware coding (`run2-real-capability-acceptance-01`) | real Claude Code worker; `code.edit` + `code.test` selected; verifier passed; retry/resume compatible |
| Real browser (`run2-real-playwright-acceptance-01`) | status=done, exit_state=success, worker=claude_code, provider=claude_subscription, retries=0; `web.browser_test` → playwright; `extra_mcp=["playwright"]`; browser opened `http://127.0.0.1:8765/`; local server logged `GET / HTTP/1.1 200`; verifier passed |

Playwright is task-specific: a normal coder launch is context7 + serena; a browser-capability
task is context7 + serena + playwright. The acceptance runs left artifact commits on local
`agentos/run2-real-*` task branches. They are evidence only and are **not** to be merged.
Repository state: private `origin` (`GokturkCan/agent-os`) exists; `feature/run2-capability-plane`
is local and not pushed (pushing/merging stays a human step).

Run 3 boundary: only the SystemOne **contract** exists. Laya, Ollaya, Jev, Decider, Kev backends,
confidence calibration and ContextGate remain future Run 3 work.

## What the CapabilityRegistry is — and is not

**Is:** the declarative truth about what each provider *can* do (capabilities), and its
operational metadata (kind, adoption, locality, cost, latency, risk, hosts, auth
requirement, integrations, probe recipe, notes/source). It lives in
`config/capability_registry.yaml`. agent-stack is still the only configuration
authority. There is no database, vector DB or registry service.

**Is not:**

- **Not a permission system.** It answers *CAN*. `config/capabilities.yaml` (protected)
  still answers *MAY*. Worker launch keeps building allowed tools, sandbox mode and the
  strict MCP set from capability profiles. A plan can only *add* an MCP server the
  worker's profile is already granted (e.g. coder holds `mcp_playwright`, readonly does not).
- **Not an orchestrator.** Hermes stays the sole global orchestrator, and
  `agentos/router.py` stays the routing authority. The plane only narrows (an
  `eligible_workers` constraint) and explains.
- **Not runtime state.** Install, availability and health never get written into the file.
  The schema rejects fields like `installed`.
- **Not a second inventory.** Records link to `workers.yaml`, `mcp.yaml` and `skills.yaml`
  through `config_ref`, and validation cross-checks those references.

## Registration ≠ installation ≠ availability ≠ health ≠ eligibility

| Concept | Where it comes from | Values |
|---|---|---|
| registered | listed in `capability_registry.yaml` | yes / no |
| adoption (decision) | registry `adoption` | adopted, benchmark, future, catalog, disabled |
| installed | probe | present, absent, unknown |
| available | probe | present, absent, unknown |
| healthy | probe (deep `--version`, or last observed `mcp.yaml` health) | healthy, unhealthy, unknown |
| authenticated | probe (`env_auth` by variable *name*; `mcp.yaml` needs_auth) | not_required, present, missing, unknown |
| eligible | policy, for one request | eligible / rejected with reason codes |

"Adopted" does **not** mean installed. Example: `ponytail` is adopted, its probe finds
nothing, so it shows as unavailable. Unknown is never upgraded. Unprobed health is
`unknown`, not `unhealthy`. By default policy, unknown health and unknown auth are allowed
but flagged (`health-unverified`, `auth-unverified`) and rank after verified candidates. A
`strict` request rejects them. Unknown *availability* is rejected by default
(`allow_unknown_availability: false`). An undeclared install never counts as available.

### Probes

`executable` (PATH or file, with optional deep `--version` that reads the exit code only),
`claude_plugin` (installed plugin index), `path` (globs), `env_auth` (non-empty variable
check; the value is never read into results, logs or output), `config_health` (last
observed `mcp.yaml` state), `service` (placeholder; Run 2 makes **no network probes**),
`declared` (no probe). Each probe is isolated. An exception becomes an `error` on that
provider and leaves its fields unknown, so the plane keeps working. Tests inject state via
`overrides`/`static_probes` and never depend on what is installed.

## Capability naming

Hierarchical, stable, lowercase, at least two dot-separated segments:
`[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+`, e.g. `code.references`, `web.docs_lookup`,
`reverse_engineering.static_analysis`. Every id must appear in the registry's
`capabilities:` catalog before a provider can declare it. Malformed or undeclared ids,
duplicate ids (including duplicate YAML keys), unknown enum values, unknown fields and
contradictions (e.g. `locality: local` on host `cloud`, `env_auth` on `auth: none`,
integrations on a non-executor) all fail `agentos validate`.

## Deterministic selection

Required capabilities = explicit ∪ task contract `required_capabilities` ∪ the policy's
`task_types` mapping (`coding`, `github`, `docs_lookup`, `browser_test`,
`reverse_engineering`). No natural-language inference and no LLM.

1. **Hard filters** per provider, each with a reason code: adoption not in
   `runtime_adoption` / denied / over a cost, locality or risk cap → `policy-blocked`;
   `host-mismatch`; `provider-unavailable`; `availability-unknown`; `provider-unhealthy`;
   `auth-missing`; strict-only `health-unknown`/`auth-unknown`.
2. **Executor coverage.** An executor is eligible only if every required capability is
   native to it or provided by an eligible tool it integrates with. Integration is the
   executor's explicit declaration (`supported`/`unsupported`/`unknown`). Failing that, a
   tool whose `requires` are native to the executor (e.g. a CLI that needs `devops.shell`)
   counts as supported. Anything else stays `unknown` and does not count. Failures report
   `capability-missing` plus `integration-unsupported` or `integration-unknown`.
3. **Ranking key** (first differing component decides, and becomes the selection reason):
   capability preference (`capability-preferred`) → verified state
   (`verified-state-preferred`) → cost `free < existing_subscription < metered < expensive
   < unknown` (`cost-preferred`) → locality `local < self_hosted < hybrid < cloud < unknown`
   (`local-preferred`) → latency (`latency-preferred`) → provider `preference`
   (`preference-order`) → id (`id-tiebreak`). Hard filters run first, so quality/risk
   constraints always override cost.
4. **Outcome.** The selected executor, the tool per capability (policy-preferred tool, then
   native, then remaining tools by rank), ordered executor and tool fallbacks, and
   capability-specific reasons (`semantic-navigation-required`, `browser-deterministic`,
   `reverse-engineering-required`). If no executor is eligible or a capability is unknown,
   the result is `status: blocked`, `exit_state: blocked`, a `handoff` list and a
   human-handoff `next_step`. The plane never guesses.

Ordering is independent of declaration order (verified by test).

### Dispatch integration (backwards compatible)

Required capabilities = `--require-capability` / contract `required_capabilities` (resume
reuses them) ∪ the registry's `task_types` mapping, via `resolve_required`. So a plain
`--type coding` dispatch plans `code.edit + code.test`. An unmapped type (e.g. `review`)
with nothing declared keeps the exact Run 1 path. Dispatch plans before routing. A blocked plan
returns `not_dispatched/blocked` before any task, worktree or worker exists. Otherwise the
plan's eligible workers narrow the router's chain (trace:
`C4: skip worker codex: not capability-eligible`). If the registry is invalid while
capabilities are declared, dispatch fails closed. If nothing is declared, an unreadable
registry only skips the mapping, with a warning on stderr. The `capability_decision` event
is emitted for declared requirements. Auto-resolved plans are recorded on the result and
TraceRecord (`capabilities`), and the contract stores only declared capabilities. That
keeps the Run 1 lifecycle event stream and task.yaml shape unchanged.

**MCP wiring.** Only MCP servers the plan selected for the *routed* worker are passed as
`extra_mcp`: providers of kind `mcp` whose `config_ref` points at a `config/mcp.yaml` entry
with a `launch` definition. Native capabilities, CLI/skill providers (e.g. repomix,
gh-cli) and launch-less MCPs (github-mcp, an HTTP plugin) never become servers.
`workers.mcp_servers_for` still checks the profile grant. **Playwright is task-specific:**
coder holds `mcp_playwright` (human-approved 2026-10-13), but `mcp.yaml exposure.coder`
stays `[context7, serena]`, so Playwright appears only when the plan selects it (e.g.
`--require-capability web.browser_test`). The result's `capabilities.extra_mcp` and
dry-run `mcp_servers` show this.

## Telemetry / explainability

Part of the existing streams, not a second subsystem:

- Event `capability_decision` (lifecycle events) carries the `capabilities` field.
- TraceRecord field `capabilities` (null unless capabilities were declared).
- Payload: `required, status, exit_state, executor, worker, routed_worker, reasons, tools,
  tool_fallbacks, eligible, fallbacks, rejected{executor: codes},
  rejected_tools{capability: {provider: codes}}, unknown_capabilities, cost, locality`.
  It holds registry ids, enum values and reason codes only. Probe details and free text are
  left out. Strings are recursively secret-redacted and truncated. Emission never raises:
  a telemetry failure leaves the selection unchanged.

`CapabilityPlan.explain()` (shown by `agentos capabilities match`) prints the selection,
per-capability tools, fallbacks and every rejection with its reason.

## CLI

```
agentos capabilities list   [--kind K] [--adoption A] [--json]
agentos capabilities show   <id> [--probe] [--json]
agentos capabilities match  <capability...> [--task-type T] [--host H] [--locality L]
                            [--max-cost C] [--max-risk R] [--deny ID] [--strict]
                            [--unavailable ID] [--unhealthy ID] [--no-auth ID]   # what-if
                            [--deep] [--record] [--json]          # exit 2 when blocked
agentos capabilities matrix [--probe] [--json]
agentos capabilities check  [--deep] [--json]
```

## Wave A inventory

Registered, with `adoption: adopted` unless noted. "Available today" is what `capabilities
check` observed on the Mac on 2026-10-13. It is a probe result, not a claim, and changes as
tools get installed.

| Provider | Kind | Capabilities | Available today |
|---|---|---|---|
| claude-code | worker | code.edit/refactor/test/debug, devops.shell/git, web.browse, skills.load | yes (binary) |
| codex | worker | code.edit/refactor/test/debug, devops.shell/git | yes (binary) |
| opencode | worker | code.edit/refactor/test/debug, devops.shell/git, skills.load | yes (binary) |
| serena | mcp | code.semantic_navigation/symbol_lookup/references/refactor/diagnostics | yes (uvx; last health ok) |
| repomix | cli | code.snapshot | yes (on demand via npx) |
| context7 | mcp | web.docs_lookup (auth optional) | yes (npx; last health ok; no key set) |
| github-mcp | mcp | devops.github | **unhealthy** (mcp.yaml: 401) |
| gh-cli | cli | devops.github (Run 1 read-only fallback) | yes (binary; auth unverified) |
| playwright | mcp | web.interact, web.browser_test, web.browse | yes (npx; last health ok) |
| rea | mcp | reverse_engineering.* (7) | unknown (not installed; no probe yet) |
| omni-macos | service | files.semantic_search, knowledge.multimodal_search | unknown (not installed) |
| superpowers | skill | engineering.workflow | yes (Claude plugin) |
| spec-kit | skill | engineering.spec | no |
| karpathy-skills | skill | engineering.guidelines | no |
| ponytail | skill | engineering.simplicity | no |
| anti-slop | skill | ui.quality_filter (filter, never an orchestrator) | no |
| last30days | skill | research.recent_signals | no |
| scientific-agent-skills | skill | research.literature_search/paper_analysis/hypothesis_generation/experiment_design/evaluation | no |
| kepano-obsidian-skills | skill | knowledge.obsidian_format | yes (Claude plugin) |
| archify | skill | visualization.architecture_diagram | unknown |
| design-md | skill | ui.design_system | no |
| 21st-dev | mcp | ui.component_registry | unknown |
| refero-styles | skill | ui.style_reference | no |
| browser-use | service | web.interact, web.browse — **adoption: future** | never selected |

Skills are metadata, not executables. Their availability is the probe result, and only
executors that declare the integration (e.g. `claude-code → superpowers: supported`) can
use them.

### Parity (R2.8): "which executor can actually satisfy this task?"

`agentos capabilities matrix` today: Claude Code reaches Serena, Context7, Playwright and
GitHub MCP (the integration is supported; the tool's own health still applies). Codex and
OpenCode have **no** Serena/Context7/Playwright/GitHub-MCP path: Agent OS launch wires no
MCP for them, and their own configs have none. That's why `code.references` today resolves
to Claude Code only. REA integration is `unknown` for every executor, so an RE task stays
blocked until one is declared. Codex skill loading is `unknown`. Not a parity claim:
anything undeclared stays unknown.

## SystemOne / FastGate contract (R2.10)

`agentos/systemone.py` is a **typed, backend-neutral contract only**. FastGate is the
abstraction, not Laya, Jev or Ollaya.

```
deterministic policy -> eligible options -> system_one(SystemOneRequest) -> SystemOneResponse
                                                                         -> execute or escalate
SystemOneRequest(task_type, state, questions, required_capabilities, eligible_options,
                 risk, cost_profile, resource_state)
SystemOneResponse(answers[Answer(question_id, choice, Confidence, reason_code)], escalate,
                  reason_code, backend)
```

Enforced by `system_one()`, independent of the backend: choices must come from
`eligible_options` (otherwise `ineligible-choice` and escalate). The deterministic hard
policy can never be bypassed. No eligible options means escalate without calling the
backend. Backend exceptions or malformed responses escalate. `NullBackend` (the default)
always escalates. `PolicyOrderBackend` is a heuristic reference that picks the policy's
first option with no confidence claim. `request_from_plan()` builds a request whose only
legal choices are a `CapabilityPlan`'s eligible executors.

**Confidence semantics.** A raw score is never a calibrated probability.
`Confidence(value, kind ∈ {none, raw, calibrated}, calibration_id)`. `calibrated` requires a
calibrator id, and `raw` may not carry one. `ConfidencePolicy(threshold, calibration_id)`
accepts **only** calibrated confidence from that calibrator, so
`if confidence > 0.92: execute` on a raw score is unrepresentable. Run 3 will measure
accuracy and ECE, then fit Platt/isotonic calibrators and workload-specific thresholds.
Nothing in Run 2 calibrates.

## ContextGate (DESIGN-ONLY)

Not implemented. Nothing in Run 2 blocks a later ContextGate (result pruner, compaction
gate, retrieval selector, relevance filter with KEEP / DROP / TRUNCATE that preserves kept
text verbatim, and learned decisions compiled into deterministic rules). It would sit
between tool output and model context and could reuse the SystemOne request/answer shape.
RTK and Headroom will be benchmarked separately. Neither is bundled.

## Deferred to Run 3

- Decision backends: Laya-MLX, Ollaya, Decider-2B, Kev-4B, OpenJev-like, Jev cloud.
- Confidence calibration (accuracy, ECE, Platt, isotonic, per-workload thresholds).
- Network/service probes (`service` probe type is a placeholder) and authenticated health
  checks for MCP services.
