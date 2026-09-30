# CURRENT_STATE — Agent OS V1 candidate

**As of:** 2026-10-01 · **Branch:** `agent-os-v1` (local only, no remote) ·
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
| Loop budgets / exit states | IMPLEMENTED, VERIFIED | wall-clock recorded, not watchdog-enforced |
| File-backed task state / resume / handoff | IMPLEMENTED, VERIFIED | `state/tasks/`, CLI + skill |
| Worktree isolation + lease | IMPLEMENTED, VERIFIED | |
| Worker launch under capability profiles | IMPLEMENTED, VERIFIED live (Claude Code, Codex) | OpenCode argv only |
| Permissions / protected manifest | IMPLEMENTED, VERIFIED | live write-denial probes on both harnesses |
| SecondBrain gate over claude-obsidian | IMPLEMENTED, VERIFIED (fixture vaults) | live vault untouched; doctor ok, lint 0 |
| Telemetry JSONL | IMPLEMENTED, VERIFIED | TTFT/RAM/VRAM not collected yet |
| Health check | IMPLEMENTED, VERIFIED | 0 FAIL, 4 WARN |
| Eval suite | IMPLEMENTED, VERIFIED | 59/59 with live |
| MSI resource profiles | IMPLEMENTED (state machine) | MSI not connected — PARTIAL |
| Hermes ↔ agentos | PARTIAL | Hermes inspected read-only; not wired to call agentos |
| Local inference (Laya, Qwen3.6, Bonsai 2) | DEFERRED (benchmark candidates) | nothing installed |
| Research plane | DESIGN-ONLY | contract in `workflows/research-question.md` |
| Self-improvement | IMPLEMENTED (gate mechanism only) | no autonomous candidate generation, by design |

## Conflicts found — need your decision (not changed by agents)

1. **Hermes default model is `moonshotai/kimi-k3` on NVIDIA NIM**, which agent-stack
   marks disabled (0-byte responses). Hermes also has **no `fallback_model`**.
2. **GitHub MCP 401** (stale static Authorization header). Postman/Stitch need auth.
3. **Plaintext z.ai token** in `~/.claude/settings.json.glm-backup` and `settings.jsonN` (from the 2026-09-15 audit).
4. **Account connectors** (Gmail/Slack/Drive/Lovable/Higgsfield/…) are exposed to *interactive*
   Claude sessions. Agent OS worker runs exclude them via `--strict-mcp-config`.
5. Overlapping planning frameworks installed: SuperClaude (`sc:*`), OpenCode GSD. Marked disabled for Agent OS; not uninstalled.
6. Stale doc claims fixed: `providers.yaml` said Codex disabled (it's logged in); architecture doc said `agents/ … scripts/` were empty.

## Where things are

- Live architecture: `docs/v1-implementation.md` (frozen design: `docs/current-architecture.md`)
- Inventories: `config/{models,providers,workers,capabilities,mcp,skills,resources,routing,knowledge,promotion,permissions}.yaml`
- Security: `docs/security-permissions.md` · Recovery: `docs/rollback-recovery.md`
- Adoption decisions: `docs/candidate-adoption.md` · Tests: `docs/acceptance-report.md`
- Task protocol: `skills/agent-os-task/SKILL.md`, `state/README.md`, `workflows/`

## Next steps (in order)

1. Decide Hermes default + fallback model (e.g. an approved provider) — config change in `~/.hermes`.
2. Link `skills/agent-os-task` into Hermes so Hermes drives `agentos` (user-config change).
3. Re-auth GitHub MCP; rotate/delete the dormant z.ai token.
4. Connect MSI (SSH alias `msi`), then benchmark Qwen3.6 → set status `measured`.
5. Benchmark Laya-MLX / Bonsai 2 on the Mac within the 6 GB model budget.
