# V1 Acceptance Test Report — 2026-10-01

Command: `AGENTOS_LIVE=1 ./scripts/run-evals.sh` on the Mac mini (macOS 27.0.1).
Result: **59 passed, 0 failed, 0 skipped** (≈15 s; live Claude test ≈12 s).
Without `AGENTOS_LIVE=1`: 58 passed, 1 skipped. Deterministic suite was run 6×
consecutively green after fixing a timestamp race (see "Defects found").

All tests use temporary state/telemetry dirs, throwaway vaults created by the
claude-obsidian engine's own `init`, and throwaway git repos. The only live-system
touches are read-only (`doctor`/`lint` on ~/SecondBrain, reading ~/.hermes/config.yaml)
and the opt-in live worker run on a temp fixture.

| # | Acceptance area | Tests | Result | What was actually executed |
|---|---|---|---|---|
| 1 | Knowledge | `test_a1_knowledge.py` (6) | **PASS** | real engine capture → raw byte-identical & idempotent; proposal refused without approval, with self-approval, wrong hash, no human ref; approved ingest writes page + both ledgers + manifest with intact sha256/source_id chain; concurrent edit after review → engine refuses, human edit preserved, nothing partially applied; proposals to `.raw`/`.vault-meta`/`inbox` refused; live vault doctor ok + lint 0 issues |
| 2 | Coding | `test_a2_coding.py` (4) | **PASS** | router → claude_code; task contract + accepted plan; worktree on `agentos/<task>` branch; second worker's lease refused; failing→passing pytest recorded; commit on task branch; main checkout untouched; clean close `success`; worktree removal refuses when leased/dirty; index-freshness stamp goes stale on edit/commit and differs per worktree. **Live:** real `claude -p` (coder profile, strict MCP) fixed the fixture bug, pytest green, only `calc.py` modified |
| 3 | Web / docs | `test_a3_web_docs.py` (10) | **PASS** | developer_docs → context7 with no browser/scraper in the trace; failing GitHub MCP → gh CLI read-only; undeployed candidates (firecrawl, repomix, browser-use, markitdown) never selected; coding workers get only context7+serena, `--strict-mcp-config`, no claude.ai connectors |
| 4 | MSI unavailable | `test_a4_msi_unavailable.py` (8) | **PASS** | health check has 0 FAIL with MSI down (INFO only); real ssh probe bounded & non-fatal; reasoning falls back to cloud; GPU workload → `blocked` with visible failure; profile transition refused when unreachable; transition steps must run in order/complete; candidate Qwen not used even with MSI up |
| 5 | Provider failure | `test_a5_provider_failure.py` (8) | **PASS** | claude_subscription down → codex; failure + fallback visible in telemetry JSONL; all down → `blocked` (no retry loop); NIM down for background escalation → `blocked`, no escalation to unapproved provider; high-risk → `human_handoff` |
| 6 | Long-task resume | `test_a6_long_task_resume.py` (5) | **PASS** | state seeded, then a **fresh process** (`python -m agentos.cli task resume`) reconstructs goal, plan, files, last test, failed hypotheses, checkpoint, iteration count; ownership conflict until handoff; `no_progress` forced after repeated identical signal; iteration/attempt budgets force `budget_exhausted`; closed tasks refuse iteration |
| 7 | Permissions | `test_a7_permissions.py` (7) + live probes | **PASS** | readonly/coder profiles never hold never-grantable caps; escalation needs operator grant with human ref (self-issued refused); launch argv encodes restrictions (Edit/Write/git push denied; codex `read-only`; bypass flag rejected); candidate workers cannot launch; policy paths protected. **Live probes:** readonly Claude Code asked to create a file → 1 permission denial, checkout unchanged; readonly Codex → sandbox refused, checkout unchanged |
| 8 | Durable lesson | `test_a8_durable_lesson.py` (5) | **PASS** | telemetry run → lesson candidate in `inbox/lessons` → captured raw → proposal → refused until independent+human approval → canonical concept page carrying run_id + evidence sha; self-improvement candidates touching evals/policy/judge rejected; stage order enforced; judge ≠ producer; canary failure → `rolled_back`; manifest drift invalidates eval; repo manifest matches |
| — | Regression | `test_regression_config.py` (5) | **PASS** | config valid; no candidate claimed usable; disabled models absent from routes; Hermes memory disabled (live read); no account connectors in worker exposure |

## Health check (live, read-only)

`./scripts/health-check.sh` → 22 checks, **0 FAIL, 4 WARN**:
Hermes default model is policy-disabled kimi-k3; Hermes has no fallback_model;
GitHub MCP 401; Postman needs auth. MSI reported INFO (unreachable, not boot-critical).

## Measured telemetry from live runs (as reported by the harness)

| Run | Latency | Tokens in/out | Cost field |
|---|---|---|---|
| Claude Code readonly permission probe | 8.6 s | 4 / 314 (+cache) | 0.156 USD as reported in Claude Code's JSON (`total_cost_usd`); may not equal subscription billing |
| Codex readonly Q&A | 13.7 s | not parsed (codex JSON usage not yet mapped) | n/a |

## Defects found and fixed during verification

1. **Plan-identity race** — claude-obsidian plans embed a 1-second `generated_at`/`operation_id`;
   dry-run and apply straddling a second failed with `PLAN_CHANGED`. Fixed by pinning both in
   `Vault.capture` (and the fixture init). Suite then 6/6 green.
2. **Headless stdin** — `codex exec` waited on stdin ("Reading additional input from stdin");
   `workers.run` now passes `stdin=DEVNULL`.
3. **Ledger identity** — first bundle used a made-up source id; the engine rejected it
   (`INVALID_PROVENANCE_LEDGER`). Now mirrors the engine's `stable_source_id`; engine re-validates.

## Not covered (not claimed)

- Hermes → agentos invocation (Hermes does not call agentos yet).
- OpenCode and DeepSeek Harness launches through agentos (argv only / external script).
- Any local-model routing (no local model measured).
- Real MSI transitions (MSI not connected).

## Addendum — Hermes integration milestone (2026-10-01)

`AGENTOS_LIVE=1 ./scripts/run-evals.sh` → **77 passed, 2 skipped** (the 2 skips are the
`hermes_wired` tests that can only run after the approved `~/.hermes/config.yaml` change).
`evals/test_hermes_integration.py`: 18 run + 2 post-approval.

Executed:
- Hermes' own `skills_list`/`skill_view`/`lint_skill`/`scan_skill` (its venv, sandbox HERMES_HOME):
  both agent-os skills discovered, loadable, 0 lint findings, guard `safe`; absent without the key.
- Proposed `skills.disabled` verified in Hermes code: bundled claude-code/codex load today, refused with it.
- `scripts/hermes-wire.py` on a copy of the live config: unapproved apply refused; approved
  apply verified; Hermes loads skills from the result; rollback restores byte-identical.
- `agentos dispatch` with stand-in workers: success → commit on `agentos/<task>` only, lease
  released, main untouched; failed verify → `retryable`, same task resumes with the resume brief;
  budget → `stopped` then `closed`; nested dispatch → `unsafe`; high risk → `human_handoff` with no
  worktree/task created; provider outage → codex with `workspace-write`; all down → `blocked`.
- **Live:** `bin/agentos dispatch` CLI → real Claude Code worker fixed the fixture, verified, `done` (~14 s).
- Live `~/.hermes/config.yaml` mtime unchanged; `~/SecondBrain` unchanged.

Not run: a Hermes-driven model turn (blocked on the Hermes default-model decision).
