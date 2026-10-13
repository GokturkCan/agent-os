# CURRENT_STATE — Agent OS V1

**As of:** 2026-10-12 · **Branch:** `agent-os-v1` (local only, no remote yet; first release will be private `GokturkCan/agent-os`) ·
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
| Worker launch under capability profiles | IMPLEMENTED, VERIFIED live (Claude Code, Codex) | OpenCode argv only |
| Permissions / protected manifest | IMPLEMENTED, VERIFIED | live write-denial probes on both harnesses |
| SecondBrain gate over claude-obsidian | IMPLEMENTED, VERIFIED (fixture vaults) | live vault untouched; doctor ok, lint 0 |
| Telemetry JSONL + lifecycle events (`agentos/events.py`) | IMPLEMENTED, VERIFIED | secret-redacted; TTFT/RAM/VRAM not collected |
| Health check | IMPLEMENTED, VERIFIED | 29 checks, 0 FAIL, 4 WARN (2026-10-13; includes `capabilities.registry`) |
| Eval suite | IMPLEMENTED, VERIFIED | latest full run (2026-10-13, Run 2 branch): **321 passed / 2 skipped** (live-only) |
| Deterministic intent routing (`agentos/intent.py`) | IMPLEMENTED, VERIFIED | read-only → normal Hermes; mutation → forced |
| Canonical entrypoint structural mutation branch (`bin/hermes-agentos` → `agentos mutate` → dispatch) | **VERIFIED** | tests + real run |
| Real mutation acceptance | **VERIFIED** | hermes-agentos → force=true → mutate → dispatch → claude_code → verifier → success |
| Real failure → retry → resume acceptance | **VERIFIED** | run 1: status=retryable, retries=1; run 2: same task/worktree, verify passed, exit_state=success |
| Real timeout → resume acceptance | **PENDING** | timeout enforcement verified by tests only; no real timeout run executed |
| Run 2 capability plane (`docs/capability-plane.md`) | IMPLEMENTED, VERIFIED by tests (2026-10-13, branch `feature/run2-capability-plane`) | registry + Wave A inventory, offline probes, deterministic selection/fallback, `capability_decision` telemetry, parity matrix, `agentos capabilities` CLI; dispatch integration opt-in (`--require-capability`), no real worker run yet |
| SystemOne/FastGate | Contract IMPLEMENTED (`agentos/systemone.py`); backends + calibration DEFERRED (Run 3) | raw confidence never treated as calibrated |
| ContextGate, Run 3 (local intelligence), Run 4 (research/web) | FUTURE / DESIGN-ONLY | see `docs/roadmap.md` |
| MSI resource profiles | IMPLEMENTED (state machine) | MSI not connected — PARTIAL |
| Hermes ↔ agentos | IMPLEMENTED, VERIFIED, **wired** (user-approved, 2026-10-01) | `skills.external_dirs` + `skills.disabled` via `scripts/hermes-wire.py`; canonical front door `bin/hermes-agentos`; Groq native completion measured (OK, 1.273s) |
| Local inference (Laya, Qwen3.6, Bonsai 2) | DEFERRED (benchmark candidates) | nothing installed |
| Research plane | DESIGN-ONLY | contract in `workflows/research-question.md` |
| Self-improvement | IMPLEMENTED (gate mechanism only) | no autonomous candidate generation, by design |

## Conflicts found — need your decision (not changed by agents)

1. **Hermes primary is now Groq `openai/gpt-oss-120b`** (native clean-room completion
   verified 2026-10-01). Fallback is intentionally unset. The current Groq account
   has an 8,000 TPM ceiling: default Hermes context exceeds it. Preloaded
   orchestration reached Claude but its quota blocked completion; see `audit/hermes-groq-milestone-2026-10-01.md`.
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
2. First private GitHub release (`GokturkCan/agent-os`): review the proposed commit groups, then push.
3. Re-auth GitHub MCP; rotate/delete the dormant z.ai token outside this repo.
4. Connect MSI (SSH alias `msi`), then benchmark Qwen3.6 → set status `measured`.
5. Benchmark Laya-MLX / Bonsai 2 on the Mac within the 6 GB model budget.
6. Run 2 follow-ups: real dispatch with `--require-capability`; review exposing plan-selected tools to worker launch. Run 3–4 per `docs/roadmap.md`.

## Hermes milestone (2026-10-01, historical)

Groq native minimal call returned `OK` in 1.273s; live Hermes primary is
`groq-gpt-oss-120b`. The earlier "context overflow" message was Groq HTTP 413
(8,451 tokens requested vs an 8,000 TPM account limit), not a model-window defect.
Automatic skill choice is unreliable; deterministic preload plus the structural
mutation branch replaced it. The 2026-10-01 dispatch was blocked by Claude quota
(task `hermes-inclusive-20261001` is preserved and must not be consumed or run);
the later real acceptance runs above supersede it for mutation and retry/resume.
Evidence summary: `audit/hermes-groq-milestone-2026-10-01.md` (raw evidence is local, git-ignored).
