# CURRENT_STATE — Agent OS V1

**As of:** 2026-10-24 (branch `feature/capability-rollout`) · **Run 3 is merged**: PR #7 (`integration/run3-final` → `main`, merge commit `a2c0897`); the Run 3 section below keeps its 2026-10-19 wording as historical record. **Release:** Agent OS **v1.0.0 is released on `main`** (merge commit `91b08aa`; product version `1.0.0` in `pyproject.toml` and `agentos.__version__`; the `version:` fields in `config/*.yaml` are file-format versions, unrelated). Run 1 and Run 2 are both included in Agent OS v1.0.0. PR #2 (Run 2 + hardening) merged into `agent-os-v1` on 2026-10-13 (UTC); PR #1 (`agent-os-v1` → `main`) merged on 2026-10-14 (local time; 2026-10-13 21:41 UTC). **The `v1.0.0` git tag and GitHub Release have not been created yet.** Remote `origin` → `GokturkCan/agent-os` is **intentionally PUBLIC** (earlier wording "private" was wrong; visibility is a human decision and must not be changed by agents). Agents never push, change remotes, merge or tag; that stays a human act. ·
**Safety tag:** `pre-agent-os-v1-mac-2026-09-30` (`b2262ec`)

Quick checks: `./scripts/health-check.sh` · `./scripts/run-evals.sh`

## Machine (audited 2026-10-01)

Mac mini M4 16 GB, macOS 27.0.1, ~65 GiB free (51 GiB on 2026-10-24). Claude Code 2.1.308 (OAuth; 2.1.280 on 2026-10-01),
Codex 0.164.0 (ChatGPT login; 0.154.0 on 2026-10-01), OpenCode 2.0.20, Hermes 0.21.3 (upstream v0.22.5), DeepSeek
Harness venv (`~/dsh-venv`), uv 0.8.4, Python 3.14. Docker installed, daemon
not running (not required). No local LLM runtime (ollama/llama.cpp/mlx).
MSI: no SSH alias → unreachable from the Mac (by design non-blocking).

## Status by component

| Component | State | Notes |
|---|---|---|
| Config as source of truth (`config/*.yaml`) | IMPLEMENTED, VERIFIED | 11 files, validated; status vocab available/configured/measured/candidate/disabled/deferred/rejected |
| Deterministic routing + fallback | IMPLEMENTED, VERIFIED | C0 → (C1/C2/C3 skipped: candidates) → C4 chains |
| Loop budgets / exit states | IMPLEMENTED, VERIFIED | attempts/iterations/no-progress enforced; worker+verifier timeouts enforced (SIGTERM→SIGKILL, process group) |
| File-backed task state / resume / handoff | IMPLEMENTED, VERIFIED | `state/tasks/`, CLI + skill |
| Worktree isolation + lease | IMPLEMENTED, VERIFIED | |
| Worker launch under capability profiles | IMPLEMENTED, VERIFIED live (Claude Code, Codex) | OpenCode disabled, fail closed (no enforcing adapter); push guarded by deny patterns (live-probed) + pre-push hook |
| Permissions / protected manifest | IMPLEMENTED, VERIFIED | live write-denial probes on both harnesses; manifest hashes 39 files (all `evals/`, permission/capability/promotion policy, worker/MCP/registry policy, launch enforcement code); `routing.yaml` is the tunable surface, its risk gate is held by `agentos validate` |
| SecondBrain gate over claude-obsidian | IMPLEMENTED, VERIFIED (fixture vaults) | live vault untouched; doctor ok, lint 0 |
| Telemetry JSONL + lifecycle events (`agentos/events.py`) | IMPLEMENTED, VERIFIED | secret-redacted; TTFT/RAM/VRAM not collected |
| Health check | IMPLEMENTED, VERIFIED | 28 checks, 0 FAIL, 3 WARN (2026-10-14; `repo.remote` is an informational PASS; the disabled OpenCode worker is no longer binary-checked) |
| Eval suite | IMPLEMENTED, VERIFIED | latest full run (2026-10-14, branch `feature/run3-local-intelligence`, R3.2C Phase 1): **658 passed / 2 skipped** (live-only); the v1.0.0 release baseline was 403 passed / 2 skipped |
| Deterministic intent routing (`agentos/intent.py`) | IMPLEMENTED, VERIFIED | read-only → normal Hermes; mutation → forced |
| Canonical entrypoint structural mutation branch (`bin/hermes-agentos` → `agentos mutate` → dispatch) | **VERIFIED** | tests + real run |
| Real mutation acceptance | **VERIFIED** | hermes-agentos → force=true → mutate → dispatch → claude_code → verifier → success |
| Real failure → retry → resume acceptance | **VERIFIED** | run 1: status=retryable, retries=1; run 2: same task/worktree, verify passed, exit_state=success |
| Real timeout → resume acceptance | **PENDING** | timeout enforcement verified by tests only; no real timeout run executed |
| Run 2 capability plane (`docs/capability-plane.md`) | **CLOSED, VERIFIED** (2026-10-13; merged into `agent-os-v1` via PR #2; included in V1) | registry + Wave A inventory, offline probes, deterministic selection/fallback, `capability_decision` telemetry, parity matrix, `agentos capabilities` CLI; dispatch plans declared caps + deterministic task_type mapping (coding → code.edit/test) and passes only plan-selected MCPs. No natural-language capability inference |
| Run 2 real worker acceptance | **VERIFIED** | real Claude Code worker, capabilities selected correctly (code.edit + code.test), verifier passed, retry/resume compatible (task `run2-real-capability-acceptance-01`) |
| Run 2 real Playwright acceptance | **VERIFIED** | task `run2-real-playwright-acceptance-01`: status=done, exit_state=success, worker=claude_code, provider=claude_subscription, retries=0; required code.edit + code.test + web.browser_test; `web.browser_test` → playwright; `extra_mcp=["playwright"]`; the browser opened `http://127.0.0.1:8765/` and the local server logged `GET / HTTP/1.1 200`; verifier passed. Playwright stays task-specific: normal coder launch = context7 + serena; browser-capability task = context7 + serena + playwright |
| SystemOne/FastGate | Contract IMPLEMENTED (Run 2); R3.1 router wiring, R3.2 adapter and Laya-MLX candidate, R3.2C–R3.2H evaluations COMPLETE (integration branch, not merged). **Outcome: NO-GO for every neural backend; production stays `NullBackend`, `tiers.fastgate.model: null`, empty protected `activation.*` allowlists.** Calibration DESIGN-ONLY (R3.3 = calibration; not started) | `fastgate` stage asks the configured backend (default `null`, always escalates; `policy-order` reference/test; adapter backends are DEFINED in the protected `config/systemone.yaml`) one typed worker question over policy-eligible options; it only narrows, never widens, the human-approval risk gate runs first, any adapter failure escalates with routing unchanged. **Selecting an adapter backend in `routing.yaml` does NOT activate it:** the router runtime guard and `agentos validate` accept it only if listed in the protected `activation.production_backends` (and a FastGate model only if in `activation.fastgate_models` AND usable); explicit-backend use is a human-invoked research path (CLI/tests) |
| ContextGate, Run 3 (local intelligence), Run 4 (research/web) | FUTURE / DESIGN-ONLY | see `docs/roadmap.md` |
| MSI resource profiles | IMPLEMENTED (state machine) | MSI not connected — PARTIAL |
| Hermes ↔ agentos | IMPLEMENTED, VERIFIED, **wired** (user-approved, 2026-10-01) | `skills.external_dirs` + `skills.disabled` via `scripts/hermes-wire.py`; canonical front door `bin/hermes-agentos`; Groq native completion measured (OK, 1.273s) |
| Laya-MLX (SystemOne backend candidate) | **RESEARCH CANDIDATE** (`models.yaml` status `candidate`, outside USABLE; operationally measured); not a default | isolated runtime `state/runtime/laya-mlx` (git-ignored, ~906 MiB): `laya-mlx` 0.4.0 (community port) + `aac6fef/laya-multilingual-mlx` @ `f2b4faf5`, MLX 0.32.3, Python 3.11.13. Warm decision p50 ~18 ms / p95 ~23 ms, cold start ~0.5 s, valid-choice rate 100%, reproducible across two runs. **Decision quality evaluated (R3.2C Phase 1, 66 labeled cases): no semantic skill demonstrated** — choices follow the label string (description-swap probe: 94.6% unchanged), reviewer independence is inverted (0/8), and on the claude_code/codex pair richer descriptions changed 48/72 → 49/72; keep as a baseline only. Evidence: `audit/laya-mlx-r3.2-2026-10-14.md` (operational), `audit/systemone-eval-r3.2c-phase1-2026-10-14.md` (quality) |
| CN-1 compute-node capability contract (`docs/compute-contract.md`) | **IMPLEMENTED Mac-side, mock-tested; no node connected** (integration branch, not merged) | protected `config/compute.yaml` holds node enablement + symbolic `endpoint_ref`/`auth_ref` (`nodes.msi.enabled: false`), capability types, offerings `{}` and authorizations `[]`; a `compute` block in the tunable `resources.yaml` is rejected. `agentos/compute.py` + `compute_jobs.py`. Nothing installed or benchmarked on the MSI; **CN-2** (real client + node service) not started. No automatic SSH/execution path |
| R3.5 efficiency patterns (`docs/efficiency-patterns.md`) | **IMPLEMENTED (opt-in, offline, not wired); measured on model-assisted fixtures** (integration branch, not merged) | ContextGate/ToolPruner/WakeGate signal coverage widened (0 essential lost on new dev/holdout; v1 unchanged), `retrieval_select.py` (BM25 + citation verifier; no embeddings), compat `trace`. Neural paths showed no gain. SystemOne stays `null`, `fastgate.model` null, allowlists empty |
| Open-Jev-2B v3 evaluation (R3.2H, `docs/openjev-research.md`) | **COMPLETE; shipped Open-Jev NO-GO, Laya NO-GO, optimised hybrid SHADOW-ONLY research candidate (not approved, not started)** | frozen 107-family v3 partitions; hybrid .759 [.631,.869] vs deterministic prefilter .667 [.545,.786] with paired delta +0.093 CI [-0.043,+0.244] (**crosses 0: not shown better than deterministic policy**); 4 disclosed fixture defects (frozen files unedited); research code lives in `scripts/openjev/`, not the production package; per-decision evidence retained as a checksum-verified archive (`audit/openjev-v3/EVIDENCE-RETENTION.md`) |
| Hermes direct-worker enforcement | VERIFIED fail-closed | live config `skills.disabled: [claude-code, codex, opencode]`; the bundled skills are also archived under `~/.hermes/skills/.archive` (never loaded). `hermes_bridge.installed_skill_dirs()` counts only ACTIVE skills; the disable-list test uses synthetic active skills (no dependence on live-home layout) and archived-skill regressions exist |
| CI | `.github/workflows/ci.yml` (offline, minimal; `docs/ci.md` lists the explicit exclusions) | necessary, not sufficient; not a security approval |
| Local inference (Qwen3.6, Bonsai 2) | DEFERRED (benchmark candidates) | nothing installed |
| Research plane | DESIGN-ONLY | contract in `workflows/research-question.md` |
| Pre-Run 4 capability rollout (`docs/capability-rollout.md`) | **APPLIED, VERIFIED; not yet committed** (branch `feature/capability-rollout`) | DONE: GitHub MCP repaired; Serena v2.1.0 / Context7 4.4.4 pinned in the user MCP config; MarkItDown 0.1.9 and Repomix 1.18.1 installed in isolated `state/runtime/*` with wrappers `bin/markitdown`, `bin/repomix`; Ponytail (2 skills, v5.3.2) vendored under `skills/`; `skills/orchestra-index` (91 skills, one standing description). Protected packet APPROVED by the owner and APPLIED 2026-10-25 (record, diffs and hashes: `audit/capability-rollout/`; manifest 77 → 78): worker-launch pins, registry corrections, `gh`/`security` denial and GitHub credential isolation for dispatched workers (defense in depth, **not a sandbox**), and fail-closed GitHub task routing (human handoff, no `gh-cli` fallback). Router: `github_structured`→`github_mcp`, `file_to_markdown`→`markitdown`, `repo_packing`→`repomix`. Dormant, untouched: OpenSpec, OmniRoute, clawdbot, SuperClaude |
| Self-improvement | IMPLEMENTED (gate mechanism only) | no autonomous candidate generation, by design |

## Conflicts found — need your decision (not changed by agents)

1. **Live Hermes primary** (read from `~/.hermes/config.yaml`, outside this repo, 2026-10-14):
   `model.default` = `nvidia/nemotron-3.5-lightning-30b-a3b` (provider `nvidia`), **no `fallback_model`**,
   memory disabled. That id is **not catalogued** in `config/models.yaml`, so the health check
   `hermes.default_model_policy` passes with status `None`; it is not a policy approval. The
   catalog/policy files (`models.yaml`, `providers.yaml`) record what was measured or approved, not
   what Hermes currently runs. Groq `openai/gpt-oss-120b` was the primary on 2026-10-01 (connectivity
   measured; the account had an 8,000 TPM ceiling); see `audit/hermes-groq-milestone-2026-10-01.md`.
2. ~~**GitHub MCP 401**~~ **REPAIRED 2026-10-24** (5/5 acceptance PASS). The 401 came from a dead PAT exported in the shell environment. Now a user-scope `github` server: Keychain-backed `headersHelper`, server-side read-only (`X-MCP-Readonly`, 22 read tools), expires 2027-01-21 (renew the Keychain item; no config change). Interactive/Hermes use only, never launched into workers. `config/mcp.yaml` now records it healthy (2026-10-25). Postman/Stitch still need auth.
3. **Plaintext z.ai token** in `~/.claude/settings.json.glm-backup` and `settings.jsonN` (from the 2026-09-15 audit). Re-checked 2026-10-24: those files are no longer present at that path (not searched elsewhere); rotate the token anyway if it was ever live.
4. **Account connectors** (Gmail/Slack/Drive/Lovable/Higgsfield/…) are exposed to *interactive*
   Claude sessions. Agent OS worker runs exclude them via `--strict-mcp-config`.
5. Overlapping planning frameworks installed: SuperClaude (`sc:*`), OpenCode GSD. Marked disabled for Agent OS; not uninstalled.
6. Stale doc claims fixed: `providers.yaml` said Codex disabled (it's logged in); architecture doc said `agents/ … scripts/` were empty.

## Where things are

- Live architecture: `docs/v1-implementation.md` (frozen design: `docs/current-architecture.md`)
- Inventories: `config/{models,providers,workers,capabilities,mcp,skills,resources,routing,knowledge,promotion,permissions}.yaml`
- Security: `SECURITY.md`, `docs/security-permissions.md` · Recovery: `docs/rollback-recovery.md`
- Adoption decisions: `docs/candidate-adoption.md` · Tests: `docs/acceptance-report.md`
- Task protocol: `skills/agent-os-task/SKILL.md`, `state/README.md`, `workflows/`

## Next steps (in order)

1. Run a real worker-timeout → resume acceptance (not yet executed).
2. Human release step: tag `v1.0.0` on `main` and publish the GitHub Release (neither exists yet). Do not merge the local `agentos/run2-real-*` acceptance-artifact branches.
3. ~~Re-auth GitHub MCP~~ (done 2026-10-24); rotate/delete the dormant z.ai token outside this repo.
4. Connect MSI (SSH alias `msi`), then benchmark Qwen3.6 → set status `measured`.
5. SystemOne: the neural-backend comparison is COMPLETE (R3.2C–R3.2H) and found no backend fit for production. Highest-value follow-up needs no model: implement the deterministic prefilter facts (reviewer ≠ author, failed-worker hand-off, interactive vs background, capability-missing, high-risk-without-approval) in the router's eligibility layer and measure them. Any shadow run first needs human-reviewed labels (v4 fixing the 4 defective families). Calibration (R3.3) only after a backend shows semantic skill.
6. ~~Run 3 release gate~~ (merged via PR #7). Next: finish the pre-Run 4 capability rollout (`docs/capability-rollout.md`, protected packet pending), then Run 4 per `docs/roadmap.md`.

## Hermes milestone (2026-10-01, historical)

Groq native minimal call returned `OK` in 1.273s; the Hermes primary at that
time was `groq-gpt-oss-120b` (it has since changed, see Conflicts #1). The earlier "context overflow" message was Groq HTTP 413
(8,451 tokens requested vs an 8,000 TPM account limit), not a model-window defect.
Automatic skill choice is unreliable; deterministic preload plus the structural
mutation branch replaced it. The 2026-10-01 dispatch was blocked by Claude quota
(task `hermes-inclusive-20261001` is preserved and must not be consumed or run);
the later real acceptance runs above supersede it for mutation and retry/resume.
Evidence summary: `audit/hermes-groq-milestone-2026-10-01.md` (raw evidence is local, git-ignored).
