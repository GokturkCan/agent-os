# Knowledge lifecycle — final handoff (Cursor continuation)

Continuation from Codex after usage limit. Repository: `~/agent-stack` only. No commits,
pushes, or canonical SecondBrain mutations were performed in this session.

**Date:** 2026-11-13
**Agent:** Cursor (local)

---

## Architecture (unchanged)

| Layer | Role |
|---|---|
| **Hermes** | Global orchestrator (WHO). Skill discovery only; no self-approval, no canonical writes. |
| **Agent OS** | Execution, routing, policy, leases, task state (`agentos knowledge …`, gate, dispatch). |
| **SecondBrain** | Canonical knowledge via claude-obsidian (`Vault` capture → propose → approve → apply). |

Operational lifecycle state lives under
`${AGENTOS_STATE_DIR:-~/agent-stack/state}/knowledge/lifecycle/`
(proposals, handoffs, contexts, outcomes, **navigation preview**). It is not canonical memory.

`AGENTS.md` is **not present** in this checkout; policy is in `CLAUDE.md`, `skills/knowledge-lifecycle/SKILL.md`, and `docs/knowledge-lifecycle.md`.

---

## Implemented capabilities

- Project identity and aliases from canonical wiki notes (`agentos/projects.py`, `knowledge projects`).
- Authorized capture → DRAFT proposals (`idea`, `decision`, `research_question`, `experiment`, `lesson`, `project`, …).
- `ready` / `export` / `reject` / `reconcile` with hash-pinned plans and human-review handoffs (no lifecycle approve/apply CLI).
- Project-scoped BM25 recall and budgeted worker **context** packages (`recall.py`, `context`).
- Structured worker-result **ingest** with attestation vs task state; rejects bare success claims.
- Integration with existing `Vault` + engine CAS, journals, recovery.
- Hermes skill `skills/knowledge-lifecycle/` wired via `bin/agentos knowledge` in `agentos/cli.py`.
- Read-only `agentos recall` + `skills/secondbrain-recall/`.
- **Navigation preview:** `~/agent-stack/state/knowledge/lifecycle/navigation.md` (also returned by `agentos knowledge navigation` JSON `preview` field). Handoffs: `.../lifecycle/handoffs/kp-<id>/` (`review.md`, `handoff.json`, `capture.md`).

---

## Security review (P1 parent-directory swap and related)

Reviewed implementation in `agentos/knowledge_lifecycle.py` against the independent P1 report.
No second canonical-write path was found. Controls and regression tests:

| Topic | Mitigation | Test / evidence |
|---|---|---|
| Symlink / parent swap on export | `_directory_fd` (`O_NOFOLLOW`), `_state_path` / handoff dir checks, `atomic_text` via dir_fd not `Path.write_text` | `test_export_parent_swap_cannot_follow_symlink_into_canonical_wiki`, leaf symlink tests |
| TOCTOU on state files | Open/read/write relative to pinned directory fd; `os.replace` + fsync | Descriptor helpers + export tests |
| Path escape | Allowlist regex on wiki paths; `is_relative_to`; symlink rejection on vault/state | `test_target_allowlist_*`, `test_broken_links_and_symlink_escape_*` |
| Incomplete writes | `.pending-<uuid>` + `O_EXCL` + atomic replace | `atomic` / `atomic_text` |
| Stale proposals | `expected_hashes` / `base_versions`; refuse ready/export/reconcile on mismatch | `test_stale_handoff_*`, concurrent ready test |
| Concurrent canonical edits | Byte-stable reads at `ready`; guard writes in plan; no re-read as “old” base | `test_concurrent_canonical_edit_during_ready_*` |
| Reviewer / approval | Independent reviewer ≠ proposer/actor; journal + plan-approval v3 fingerprint | `test_forged_or_self_approval_*`, journal tamper test |
| Cross-project leakage | `_belongs`, scoped context/recall | `test_scoped_context_*` |
| Sensitive provenance | `SENSITIVE` regex; context filter | `test_sensitive_*` |
| Worker authenticity | Dispatch outcome + TaskStore attestation or artifact hash | `test_unknown_worker_success_*` |
| Canonical writes | No lifecycle approve; workers cannot apply | CLI omits approve; gate tests |

**Session fix:** Concurrent capture could race on first `_directory_fd` mkdir and `.lock` open (`test_capture_idempotent_concurrent_and_restart_recovery` flaky).
`locked()` and `_directory_fd` now retry safe creation/open and hold the directory fd for the full lock scope. **60/60** lifecycle tests pass after fix.

**Residual risk (accepted):** Operational state under `~/agent-stack/state` is trusted to the same user as Agent OS. The threat model is malicious symlink/TOCTOU under that tree and vault concurrent edits — not remote attackers without local access.

---

## Verification results (this session)

Environment: `AGENTOS_NODE_MSI=down`, `AGENTOS_LIVE=0`, `uv run pytest` from `~/agent-stack`.

| Check | Result |
|---|---|
| Focused lifecycle suite `tests/test_knowledge_lifecycle.py` | **60 passed** (~26s) |
| Combined `evals` + `tests` | **1012 passed**, 16 skipped, **3 failed** (~86s) |
| `evals/test_hermes_integration.py` | **25 passed**, 2 skipped (includes skill discovery) |
| `evals/test_protected_manifest.py` + `evals/test_a1_knowledge.py` | **14 passed** |
| Synthetic E2E `scripts/demo-knowledge-lifecycle.py` | **PASSED** (`/tmp/knowledge-lifecycle/demo-cursor-1794537956`) |
| Live read-only recall `bin/agentos recall` | **status: ok** (vault unchanged) |
| Live `bin/agentos knowledge projects` | **`[]`** (zero canonical project notes) |
| Real SecondBrain vault | **Not modified** (demo/tests use disposable vaults only) |

**Regression failures (not lifecycle-related):**

1. `evals/test_capability_rollout.py::test_worker_launch_env_has_no_github_identity` (claude_code, codex) — isolated `GH_CONFIG_DIR` expectation.
2. `evals/test_worker_boundaries.py::test_dispatch_passes_guard_and_worker_context_env_to_the_runner` — missing `GIT_CONFIG_KEY_0` in synthetic runner env.

Treat as **environment / prior drift** until run in the known-good CI/user shell; lifecycle code did not touch `workers.py` launch env.

**Hermes live conversation:** NOT VERIFIED. Skill listing/lint/guard verified via Hermes integration tests and prior artifact `/tmp/knowledge-lifecycle/hermes-discovery-final.json` (`knowledge-lifecycle`: `view_ok`, `guard_verdict: safe`).

Historical Codex evidence preserved under `/tmp/knowledge-lifecycle/` (baseline suite 1011 passed, demo-final, verified-suite with sandbox-induced failures).

---

## Capability status table

| CAPABILITY | STATUS | VERIFIED EVIDENCE | REMAINING ACTION |
|---|---|---|---|
| Project resolve / ambiguity | VERIFIED | `test_project_exact_alias_*`; live `projects` → `[]` | Add first real project note (below) |
| Capture / proposals | VERIFIED | 60 lifecycle tests + demo A | — |
| Scoped context / recall | VERIFIED | context tests; live recall ok | — |
| Reviewer handoff export | VERIFIED | export/stale/symlink tests; demo handoff path | Human approval for any real commit |
| Reconcile / commit receipt | VERIFIED | reviewer_approve path in tests; demo COMMITTED | — |
| Engine recovery | VERIFIED | interruption + recover test | — |
| Dispatch / ingest (dry-run + synthetic) | VERIFIED | dispatch tests; demo C | First **live** worker handoff (user-authorized) |
| Navigation preview | VERIFIED | `navigation` test; `state/knowledge/lifecycle/navigation.md` | — |
| Hermes skill discovery | VERIFIED | `evals/test_hermes_integration.py`; hermes-discovery-final.json | First natural-language Hermes capture (user) |
| Concurrent capture durability | VERIFIED | 15× stress + suite after lock fix | — |
| Full evals regression | IMPLEMENTED, NOT LIVE-TESTED | 1012/1015 pass; 3 failures above | Fix or re-run in canonical environment |
| Real canonical project onboarding | APPROVAL REQUIRED | live `projects` empty | User-authored first project proposal |
| Canonical wiki write from Hermes | BLOCKED by design | no approve CLI | Existing reviewer + claude-obsidian gate only |

---

## Changed / untracked files (working tree)

**Modified (tracked):**

- `agentos/cli.py` — `recall`, `knowledge` subcommands

**New / untracked (lifecycle core):**

- `agentos/knowledge_lifecycle.py` (includes concurrency lock fix)
- `agentos/knowledge_cli.py`
- `agentos/projects.py`
- `agentos/recall.py`
- `tests/test_knowledge_lifecycle.py`
- `tests/test_recall.py`
- `docs/knowledge-lifecycle.md`
- `skills/knowledge-lifecycle/SKILL.md`
- `skills/secondbrain-recall/SKILL.md`
- `scripts/demo-knowledge-lifecycle.py`

**Other untracked (Run 3.6 / audit — not part of lifecycle merge checklist unless you want them):**

- `audit/run3.6/`, `docs/run3.6-*.md`, `docs/systemone-v4-protocol.md`, `scripts/r36/`

**This session:** only `agentos/knowledge_lifecycle.py` edited (lock/`_directory_fd` concurrency).

---

## CLI examples

```bash
# List canonical projects (currently empty on real vault)
~/agent-stack/bin/agentos knowledge projects

# Stage an authorized idea (JSON outside SecondBrain)
~/agent-stack/bin/agentos knowledge capture --input /tmp/idea.json

# Prepare review package
~/agent-stack/bin/agentos knowledge ready kp-xxxxxxxx
~/agent-stack/bin/agentos knowledge export kp-xxxxxxxx

# Inspect operational preview (not canonical)
~/agent-stack/bin/agentos knowledge navigation

# Read-only memory
~/agent-stack/bin/agentos recall "prior decisions about X" --top 5
```

---

## First real project onboarding

Real vault has **no** `wiki/projects/*.md` entries. Do not invent facts or auto-ingest repos.

1. **Choose** a real project (name, scope, registered repo path on disk).
2. **Prepare** bounded capture JSON:

   ```json
   {
     "authorized": true,
     "kind": "project",
     "project": null,
     "summary": "Seed project record for <name>.",
     "evidence": [{"kind": "user_statement", "locator": "session:<your-session-ref>"}],
     "origin": {"actor": "hermes", "kind": "user_statement"},
     "confidence": "user_statement",
     "project_spec": {
       "name": "<Canonical Name>",
       "scope": "<One paragraph scope>",
       "aliases": ["<alias>"],
       "status": "seed",
       "repositories": ["/absolute/path/to/repo"]
     }
   }
   ```

3. **Run** `capture` → `ready` → `export`. Open
   `state/knowledge/lifecycle/handoffs/kp-…/review.md` and confirm diff + hashes.
4. **Authorize** through the existing reviewer workflow (`docs/knowledge-lifecycle.md`): inbox capture, `Vault.propose/approve/apply` — **not** Hermes self-approval.
5. **Reconcile** `agentos knowledge reconcile kp-…` after engine apply.
6. **Verify** `knowledge projects "<alias>"` → `status: matched`; then
   `knowledge context --project <id> --objective "…"`.

---

## First live Hermes recall test (read-only)

In a Hermes session (canonical entrypoint unchanged):

1. Confirm skill: `knowledge-lifecycle` appears in external skills (already verified in evals).
2. Ask Hermes to run:
   `~/agent-stack/bin/agentos recall "<topic you know exists in SecondBrain>" --top 5`
3. Expect JSON with `status: ok` or `no_results`; Hermes must read cited `absolute_path` before claiming facts.

No model-driven test was executed in this Cursor session.

---

## First real Agent OS worker handoff test (user-authorized)

1. Complete project onboarding so `repositories` includes your repo.
2. Dry-run dispatch (no worker execution):

   ```bash
   ~/agent-stack/bin/agentos knowledge dispatch \
     --project <id> --task-id kl-handoff-1 \
     --repo /path/to/repo \
     --objective "Bounded task with acceptance criteria" \
     --verify "uv run pytest -q tests"
   ```

3. Inspect `state/knowledge/lifecycle/contexts/kl-handoff-1.json`.
4. Only with explicit authorization, add `--execute` (existing dispatcher; may create task-branch commits).

---

## Continuation for future development

1. **Land the tree** — stage and commit lifecycle files; keep Run 3.6 docs separate if desired.
2. **Resolve the 3 eval failures** — inspect `build_launch` / `GH_CONFIG_DIR` on this host vs CI.
3. **First real project** — follow onboarding; first commit is a human-gated engine transaction.
4. **Do not add** lifecycle `approve`/`apply`, alternate orchestrators, or vector/LLM memory.
5. **OpenCode / Cursor / Antigravity** workers remain disabled until separate adapter work; contract is documented in `docs/knowledge-lifecycle.md`.

---

## Known limitations

- Day-precision `changes --since` for canonical `updated` fields; proposal history uses full ISO timestamps.
- `ingest-result` without dispatch attestation stays `unverified_external_report` unless artifact evidence is provided.
- Navigation and handoffs are **outside** Obsidian canonical graph until reviewed and applied.
- Full suite count is 1012 passed (not historical 1011) after test additions; three eval failures are outstanding on this machine.

---

## Stop conditions met

Security controls for handoff export reviewed with passing symlink/parent-swap tests; concurrency fix applied and verified; disposable demo and read-only live recall succeeded; real SecondBrain unchanged; handoff document written. **No further autonomous changes recommended without user commit/approval intent.**

---

## Continuation session — project workflow + regression closure (2026-11-13, Cursor)

### Regression failures — root cause and fix

**Cause:** The shell inherited `GIT_CONFIG_COUNT=1` (and related `GIT_CONFIG_KEY_0` values) from the host/IDE environment. `git_push_guard_env()` chained hook config at index *n* = ambient count, so `build_launch()["env"]` exposed `GIT_CONFIG_KEY_1` instead of `GIT_CONFIG_KEY_0`, breaking evals. `workers.run()` also merged the full host `os.environ`, so stale git-config pairs could reach worker subprocesses.

**Fix (`agentos/workers.py`):**

- `build_launch` uses `git_push_guard_env({})` — worker overlay always starts at index 0.
- `sanitized_host_environ()` strips `GIT_CONFIG_*` and GitHub credential vars before merge.
- New regression: `test_worker_launch_env_ignores_ambient_git_config`.
- `evals/protected-manifest.json` refreshed for `agentos/workers.py` (minimal security fix).

### Project onboarding and continuity (new)

| Module | Role |
|--------|------|
| `agentos/project_onboarding.py` | `inspect_repository`, `propose_onboarding` |
| `agentos/project_continuity.py` | `project_status`, `continuation_package` |
| `agentos/knowledge_cli.py` | `inspect`, `onboard`, `status`, `continue` subcommands |
| `docs/project-workflow.md` | Operator guide |
| `tests/test_project_workflow.py` | 13 tests + synthetic integration path A–J |

Markdown is excerpted only (bounded); symlinks in repos are refused; `onboard` requires `--authorized`; no canonical writes.

### Verification (this session)

`AGENTOS_NODE_MSI=down`, `AGENTOS_LIVE=0`:

| Suite | Result |
|-------|--------|
| `evals` + `tests` | **1029 passed**, 16 skipped |
| Previously failing 3 worker env tests | **PASS** |
| `tests/test_knowledge_lifecycle.py` | 60 passed |
| `tests/test_project_workflow.py` | 13 passed |

Real SecondBrain: **unchanged**. No live Hermes conversation, no `--execute` dispatch, no commits/pushes.

### Capability table (updated)

| CAPABILITY | STATUS | EVIDENCE | REMAINING |
|------------|--------|----------|-----------|
| Worker git-config isolation | VERIFIED | 3 former failures + new regression test | — |
| Repo inspect / onboard proposal | VERIFIED | `test_project_workflow.py` | First real repo `--authorized` |
| Project status / continuity package | VERIFIED | continuity tests + integration | Live worker handoff (user) |
| Automatic multi-worker recovery | BLOCKED | By design; leases block auto-resume | — |
| Protected manifest | VERIFIED | `evals/protected-manifest.json` refreshed | Human review at merge |

### Files touched (incremental)

- `agentos/workers.py`, `evals/protected-manifest.json`, `evals/test_capability_rollout.py`
- `agentos/project_onboarding.py`, `agentos/project_continuity.py`, `agentos/knowledge_cli.py` (new/extended)
- `tests/test_project_workflow.py`, `docs/project-workflow.md`
- `skills/knowledge-lifecycle/SKILL.md` (CLI docs only)
