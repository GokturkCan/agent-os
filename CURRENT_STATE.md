# CURRENT_STATE — Agent OS V1

**As of:** 2026-10-14 · **Release:** Agent OS **v1.0.0 release candidate** on `agent-os-v1` (product version `1.0.0` in `pyproject.toml` and `agentos.__version__`; the `version:` fields in `config/*.yaml` are file-format versions, unrelated). Run 1 and Run 2 are both included in V1; Run 3 is future work. PR #2 (Run 2 + hardening) was merged into `agent-os-v1` on 2026-10-13; PR #1 (`agent-os-v1` → `main`) is open. **`main` has not been updated and the `v1.0.0` tag / GitHub release do not exist yet.** Private remote `origin` → `GokturkCan/agent-os`. Agents never push, change remotes, merge or tag; that stays a human act. ·
**Safety tag:** `pre-agent-os-v1-mac-2026-09-30` (`b2262ec`)

Quick checks: `./scripts/health-check.sh` · `./scripts/run-evals.sh`

## Machine (audited 2026-10-01)

Mac mini M4 16 GB, macOS 27.0.1, ~65 GiB free. Claude Code 2.1.280 (OAuth),
Codex 0.154.0 (ChatGPT login), OpenCode 2.0.20, Hermes 0.21.3, DeepSeek
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
| Eval suite | IMPLEMENTED, VERIFIED | latest full run (2026-10-14, Run 2 branch after pre-release hardening): **403 passed / 2 skipped** (live-only) |
| Deterministic intent routing (`agentos/intent.py`) | IMPLEMENTED, VERIFIED | read-only → normal Hermes; mutation → forced |
| Canonical entrypoint structural mutation branch (`bin/hermes-agentos` → `agentos mutate` → dispatch) | **VERIFIED** | tests + real run |
| Real mutation acceptance | **VERIFIED** | hermes-agentos → force=true → mutate → dispatch → claude_code → verifier → success |
| Real failure → retry → resume acceptance | **VERIFIED** | run 1: status=retryable, retries=1; run 2: same task/worktree, verify passed, exit_state=success |
| Real timeout → resume acceptance | **PENDING** | timeout enforcement verified by tests only; no real timeout run executed |
| Run 2 capability plane (`docs/capability-plane.md`) | **CLOSED, VERIFIED** (2026-10-13; merged into `agent-os-v1` via PR #2; included in V1) | registry + Wave A inventory, offline probes, deterministic selection/fallback, `capability_decision` telemetry, parity matrix, `agentos capabilities` CLI; dispatch plans declared caps + deterministic task_type mapping (coding → code.edit/test) and passes only plan-selected MCPs. No natural-language capability inference |
| Run 2 real worker acceptance | **VERIFIED** | real Claude Code worker, capabilities selected correctly (code.edit + code.test), verifier passed, retry/resume compatible (task `run2-real-capability-acceptance-01`) |
| Run 2 real Playwright acceptance | **VERIFIED** | task `run2-real-playwright-acceptance-01`: status=done, exit_state=success, worker=claude_code, provider=claude_subscription, retries=0; required code.edit + code.test + web.browser_test; `web.browser_test` → playwright; `extra_mcp=["playwright"]`; the browser opened `http://127.0.0.1:8765/` and the local server logged `GET / HTTP/1.1 200`; verifier passed. Playwright stays task-specific: normal coder launch = context7 + serena; browser-capability task = context7 + serena + playwright |
| SystemOne/FastGate | Contract IMPLEMENTED (`agentos/systemone.py`); backends + calibration DEFERRED (Run 3) | raw confidence never treated as calibrated; Laya/Ollaya/Jev/Decider/Kev backends, calibration and ContextGate are future Run 3 work |
| ContextGate, Run 3 (local intelligence), Run 4 (research/web) | FUTURE / DESIGN-ONLY | see `docs/roadmap.md` |
| MSI resource profiles | IMPLEMENTED (state machine) | MSI not connected — PARTIAL |
| Hermes ↔ agentos | IMPLEMENTED, VERIFIED, **wired** (user-approved, 2026-10-01) | `skills.external_dirs` + `skills.disabled` via `scripts/hermes-wire.py`; canonical front door `bin/hermes-agentos`; Groq native completion measured (OK, 1.273s) |
| Local inference (Laya, Qwen3.6, Bonsai 2) | DEFERRED (benchmark candidates) | nothing installed |
| Research plane | DESIGN-ONLY | contract in `workflows/research-question.md` |
| Self-improvement | IMPLEMENTED (gate mechanism only) | no autonomous candidate generation, by design |

## Conflicts found — need your decision (not changed by agents)

1. **Live Hermes primary** (read from `~/.hermes/config.yaml`, outside this repo, 2026-10-14):
   `model.default` = `nvidia/nemotron-3.5-lightning-30b-a3b` (provider `nvidia`), **no `fallback_model`**,
   memory disabled. That id is **not catalogued** in `config/models.yaml`, so the health check
   `hermes.default_model_policy` passes with status `None`; it is not a policy approval. The
   catalog/policy files (`models.yaml`, `providers.yaml`) record what was measured or approved, not
   what Hermes currently runs. Groq `openai/gpt-oss-120b` was the primary on 2026-10-01 (connectivity
   measured; the account had an 8,000 TPM ceiling); see `audit/hermes-groq-milestone-2026-10-01.md`.
2. **GitHub MCP 401** (stale static Authorization header). Postman/Stitch need auth.
3. **Plaintext z.ai token** in `~/.claude/settings.json.glm-backup` and `settings.jsonN` (from the 2026-09-15 audit).
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
2. Human release sequence: review/merge PR #1 (`agent-os-v1` → `main`, merge commit), then tag `v1.0.0` and publish the release. Do not merge the local `agentos/run2-real-*` acceptance-artifact branches.
3. Re-auth GitHub MCP; rotate/delete the dormant z.ai token outside this repo.
4. Connect MSI (SSH alias `msi`), then benchmark Qwen3.6 → set status `measured`.
5. Benchmark Laya-MLX / Bonsai 2 on the Mac within the 6 GB model budget.
6. Run 3–4 per `docs/roadmap.md` (Run 2 is closed).

## Hermes milestone (2026-10-01, historical)

Groq native minimal call returned `OK` in 1.273s; the Hermes primary at that
time was `groq-gpt-oss-120b` (it has since changed, see Conflicts #1). The earlier "context overflow" message was Groq HTTP 413
(8,451 tokens requested vs an 8,000 TPM account limit), not a model-window defect.
Automatic skill choice is unreliable; deterministic preload plus the structural
mutation branch replaced it. The 2026-10-01 dispatch was blocked by Claude quota
(task `hermes-inclusive-20261001` is preserved and must not be consumed or run);
the later real acceptance runs above supersede it for mutation and retry/resume.
Evidence summary: `audit/hermes-groq-milestone-2026-10-01.md` (raw evidence is local, git-ignored).
