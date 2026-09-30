# Agent OS V1 — Live Implementation

**Status:** describes what is actually implemented on this Mac as of
2026-10-01. The frozen architecture is in `docs/current-architecture.md`;
this document does not change it — it maps each piece to real code/config and
says honestly what is not built.

Labels: **IMPLEMENTED** (code exists) · **VERIFIED** (executed test/evidence) ·
**PARTIAL** · **DESIGN-ONLY** · **DEFERRED**.

## 1. Shape

```
Hermes (orchestrator, ~/.hermes)          ← not yet calling agentos (PARTIAL)
   │  uv run agentos route | task | health
   ▼
~/agent-stack
   config/*.yaml   canonical, machine-readable, validated (agentos.config)
   agentos/        deterministic control-plane library + CLI
   evals/          executable acceptance/regression suite (+ protected manifest)
   state/          runtime state, git-ignored (tasks, telemetry, approvals, ...)
   │
   ├── workers ──► claude -p / codex exec / opencode run  (in task worktrees)
   └── knowledge ► claude-obsidian engine ──► ~/SecondBrain (wiki via transactions only)
```

No new service, daemon, database or orchestrator was added. Runtime deps:
Python ≥3.11 + PyYAML (+ pytest for evals), managed by `uv` (`pyproject.toml`, `uv.lock`).

## 2. Module map

| Concern | File | Status |
|---|---|---|
| Config load + structural validation (status vocab, cross-refs, MSI-not-boot-critical, no never-grantable grants) | `agentos/config.py` | IMPLEMENTED, VERIFIED |
| Deterministic routing: C0 rules → fastgate → local → cloud chain; tool-need routing | `agentos/router.py`, `config/routing.yaml` | IMPLEMENTED, VERIFIED |
| Loop budgets (attempts/iterations/no-progress/wall-clock) | `config/routing.yaml` `budgets`, enforced in `taskstate.py` | IMPLEMENTED, VERIFIED (wall-clock recorded, not enforced by a timer) |
| File-backed long-task state, checkpoints, handoff, resume | `agentos/taskstate.py`, `state/README.md` | IMPLEMENTED, VERIFIED |
| Worktree isolation + single-owner lease + index freshness stamp | `agentos/worktree.py` | IMPLEMENTED, VERIFIED |
| Worker launch under capability profile (strict MCP, tool allow/deny, sandbox) | `agentos/workers.py`, `config/workers.yaml`, `config/capabilities.yaml` | IMPLEMENTED, VERIFIED live for Claude Code + Codex |
| Permission checks, escalation grants, protected paths | `agentos/permissions.py` | IMPLEMENTED, VERIFIED |
| SecondBrain gate (capture → propose → approve → apply → lint) | `agentos/knowledge.py`, `config/knowledge.yaml` | IMPLEMENTED, VERIFIED on fixture vaults |
| Telemetry (JSONL TraceRecord, measured fields only) | `agentos/telemetry.py` | IMPLEMENTED, VERIFIED |
| MSI reachability + profile transitions | `agentos/resources.py`, `config/resources.yaml` | IMPLEMENTED; MSI not connected |
| Lessons + self-improvement gate + protected manifest | `agentos/selfimprove.py`, `config/promotion.yaml`, `evals/protected-manifest.json` | IMPLEMENTED, VERIFIED (mechanism; no autonomous loop) |
| Health check | `agentos/health.py`, `scripts/health-check.sh` | IMPLEMENTED, VERIFIED |

## 3. Cognition routing as built

| Stage | Today | Why |
|---|---|---|
| C0 deterministic rules | active (exit codes, test results, resource/health checks, cron, renames) | no model needed |
| C1 FastGate (Laya) | **skipped** by router with trace "no usable model" | Laya not installed/measured |
| C2 Qwen3.6 on MSI | **skipped** | MSI unreachable; model unmeasured |
| C3 Bonsai 2 on Mac | **skipped** | no runtime/weights |
| C4 cloud | claude_subscription → codex_subscription (via their harnesses); nvidia_nim for background coding escalation only | available/measured |

When Laya/Qwen/Bonsai are benchmarked, setting the tier `model` and status
`measured` in `config/models.yaml` (plus enabling the local provider) is all
that is needed — no code change. The regression suite refuses local providers
being enabled without a measured model.

## 4. Knowledge plane as built

`agentos` never writes `wiki/`. It builds claude-obsidian transaction bundles
whose `expected_hashes` pin the pre-state; the engine's `inspect` yields an
`approval_sha256`; `Vault.approve` requires a reviewer different from the
proposer, the exact hash, and a human approval reference; `Vault.apply` calls
the engine, which refuses if any target changed (compare-and-swap) and journals
backups. Ledger entries use the engine's canonical `stable_source_id`
(`file` + raw locator + sha256), which the engine re-validates.

Live vault state was **not modified** by this implementation (verified: no
files under `~/SecondBrain` newer than the implementation start, excluding the
`remember` plugin's own `.remember/`).

## 5. Execution plane as built

- One task → one worktree (`agentos/<task_id>` branch) → one lease holder.
- Claude Code: `--strict-mcp-config` with only profile-exposed MCPs
  (coder/readonly: context7, serena), explicit `--allowedTools` /
  `--disallowedTools` (git push/remote, rm -rf, sudo always denied).
- Codex: `--sandbox read-only|workspace-write` by profile; the bypass flag is rejected.
- OpenCode: argv only; `--auto` is rejected; GSD pack is disabled by policy.
- DeepSeek Harness: measured separately; background escalation route only.

## 6. Simplicity policy (Ponytail intent, until Ponytail itself is installed)

Prefer the smallest change that passes deterministic verification; no new
abstraction without two concrete users; no new dependency without a failing
test that needs it; delete before adding. (Superpowers governs *process*;
this governs *output size*.)

## 7. Not built (honest gaps)

- Hermes does not call `agentos` yet (needs a Hermes skill link — user config change).
- No local inference (Laya/Qwen/Bonsai) — candidates only.
- MSI not connected (no SSH alias); resource transitions are verified as a state machine only.
- Wall-clock budgets recorded but not enforced by a watchdog.
- Telemetry has no TTFT/RAM/VRAM collection yet (fields exist, stay null).
- Research plane: interface contract only (`workflows/research-question.md`).
- Self-improvement: gate mechanism only; nothing generates candidates automatically (by design for V1).
