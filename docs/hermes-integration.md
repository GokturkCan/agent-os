# Hermes → Agent OS integration

**Status (2026-10-01):** skills wiring and direct-worker skill disabling are
applied and verified. Groq native minimal completion succeeded; the live primary
is now `groq-gpt-oss-120b` / `openai/gpt-oss-120b`, with fallback intentionally
unset. First real Hermes → Agent OS → Claude launch was measured; successful
completion is blocked by Claude subscription quota. Automatic skill selection
also remains unreliable. See `audit/hermes-groq-milestone-2026-10-01.md`.

The approval/apply instructions below are historical wiring documentation; do
not reapply them as a pending change. For bounded acceptance, Hermes' native
`--skills agent-os-orchestrate` preload was used in a disposable home. The live
default toolset exceeds the current Groq 8,000 TPM quota even on a fresh turn;
this integration is not yet approved for normal unattended operation.

## Shape

```
user ─► Hermes (sole orchestrator: decides what/who, owns the conversation)
          │  loads skills from ~/agent-stack/skills via skills.external_dirs
          │  terminal: ~/agent-stack/bin/agentos <route|dispatch|task|health|lesson>
          ▼
        agentos (policy + execution layer; never calls Hermes, never merges/pushes)
          route → risk gate → task state → worktree+lease → worker (capability profile)
          → verify → local commit on agentos/<task> → telemetry → JSON back to Hermes
          │
          └─ worker processes run with AGENTOS_WORKER_CONTEXT set → nested dispatch refused (cooperative env guard, see security-permissions.md)
```

- **Smallest integration point:** Hermes' `skills.external_dirs`, one list entry.
  Hermes already has `terminal` + `skills` toolsets enabled for the CLI, so no
  toolset, plugin, hook, MCP server, gateway or model change is needed.
- **Single orchestrator preserved:** agentos has no code path that starts Hermes
  (static test); `hermes_delegation` is not a selectable worker; workers can't
  dispatch (runtime guard + test).
- **MSI/local models:** untouched and optional; dispatch routes to cloud workers today.

## Implemented in agent-stack (verified)

| Piece | File | Test |
|---|---|---|
| `agentos dispatch` (Hermes' execution entry) | `agentos/dispatch.py`, `agentos/cli.py` | `test_dispatch_*`, `test_budget_stops_retry_loop`, `test_nested_dispatch_from_worker_is_refused`, `test_high_risk_*`, `test_provider_outage_*`, live `test_live_dispatch_cli_with_claude` |
| `agentos lesson` (lesson candidate → SecondBrain inbox) | `agentos/cli.py` | covered by `test_a8_*` pipeline |
| Wrapper usable from any cwd | `bin/agentos` | `test_wrapper_runs_from_any_directory` |
| Hermes-facing skill | `skills/agent-os-orchestrate/SKILL.md` | Hermes' own discovery + linter (0 warnings) + guard (`safe`) in a sandbox HERMES_HOME |
| Worker-facing skill (Hermes-format frontmatter) | `skills/agent-os-task/SKILL.md` | same |
| Read-only Hermes bridge + health checks | `agentos/hermes_bridge.py`, `agentos/health.py` | `test_probe_never_touches_live_hermes_home`, health `hermes.*` |
| Approved-change tooling (human-run) | `scripts/hermes-wire.py` | `test_wire_script_apply_verify_rollback_on_copy` (apply → verify → Hermes loads → rollback byte-identical, on a copy) |

Findings from rehearsal that shaped the tooling:

- `hermes config set` rewrites the file and **drops its trailing comment block**
  (the commented "Fallback Model" help). `hermes-wire.py` inserts text instead.
- Hermes' validator calls `skills.disabled` "not a recognized config key", but
  its skill loader honours it: with the key set, `claude-code`/`codex` vanish
  from the index and `skill_view` returns "Skill 'claude-code' is disabled"
  (`test_proposed_disable_list_blocks_direct_worker_skills`).
- Long dispatches exceed Hermes' 180 s foreground terminal timeout; the skill tells
  Hermes to use `background=true, notify=true` (Hermes feature, no config change).

## ⛔ Approval boundary

### File

`~/.hermes/config.yaml`, top-level `skills:` block. No other file, no credentials,
no provider/model keys, no `.env`, no auth.

### Change 1 (required): `skills.external_dirs`

| | |
|---|---|
| Current | unset in file; resolved value `[]` (`hermes config get skills` → `external_dirs: []`) |
| Proposed | `["~/agent-stack/skills"]` |
| Why | This is the only way Hermes can see `agent-os-orchestrate` and `agent-os-task`. Without it, Hermes does not know agentos exists, so it keeps choosing workers itself. |

### Change 2 (recommended, separable with `--no-disable`): `skills.disabled`

| | |
|---|---|
| Current | unset (no skills disabled) |
| Proposed | `["claude-code", "codex", "opencode"]` |
| Why | These bundled Hermes skills teach Hermes to launch `claude -p` / `codex exec` / `opencode` directly (e.g. with broad `--allowedTools`). That bypasses capability profiles, worktree isolation, budgets and verification. The Agent OS skill only asks Hermes not to launch workers directly; disabling these skills enforces it. The skill files stay on disk. |

### Exact diff (from `scripts/hermes-wire.py plan`)

```diff
@@ -130,6 +130,12 @@
 delegation:
   max_iterations: 250
 skills:
+  external_dirs:
+    - ~/agent-stack/skills
+  disabled:
+    - claude-code
+    - codex
+    - opencode
   creation_nudge_interval: 15
 approvals:
   mode: smart
```

### Apply (you run it, or tell me to)

```
uv run --project ~/agent-stack python ~/agent-stack/scripts/hermes-wire.py plan
uv run --project ~/agent-stack python ~/agent-stack/scripts/hermes-wire.py apply --i-approve             # both keys
uv run --project ~/agent-stack python ~/agent-stack/scripts/hermes-wire.py apply --i-approve --no-disable  # required key only
```

This writes a backup to `~/.hermes/config.yaml.backup-before-agentos-<timestamp>`,
inserts the lines, and checks that the file parses and that nothing except
those keys changed. If that check fails, it restores the backup automatically.

### Rollback

```
uv run --project ~/agent-stack python ~/agent-stack/scripts/hermes-wire.py rollback
# or manually:
cp "$(ls -t ~/.hermes/config.yaml.backup-before-agentos-* | head -1)" ~/.hermes/config.yaml
```

### Tests run afterward

```
~/agent-stack/bin/agentos health             # expect hermes.agentos_skills_wired PASS, hermes.direct_worker_skills PASS, 0 FAIL
cd ~/agent-stack && uv run pytest -q -rs evals/test_hermes_integration.py
                                              # the 2 `hermes_wired` tests stop skipping and must pass
cd ~/agent-stack && ./scripts/run-evals.sh   # full suite, 0 failures
hermes skills list | grep agent-os            # real Hermes lists agent-os-orchestrate + agent-os-task, enabled
hermes config get skills                      # shows the two keys; memory stays disabled
```

### Not part of this approval (separate decision)

A live Hermes-driven turn (`bin/hermes-agentos "..."` using the skill) needs a working
Hermes model. Hermes' default today is `moonshotai/kimi-k3`, which agent-stack
marks disabled (0-byte responses), and it has no `fallback_model`. That is a
model/provider decision, kept separate from this change on purpose.

## Canonical entrypoint

`~/agent-stack/bin/hermes-agentos "request" [extra args]` is the canonical
Agent OS → Hermes entrypoint. It runs the deterministic intent gate
(`config/routing.yaml` `intent_rules`, inspect with `agentos intent --text "..."`)
and routes clear repository-mutation requests **structurally**: the wrapper `exec`s
`agentos mutate` → `agentos dispatch` → worker → verifier and never starts Hermes,
so Hermes `patch`/`write_file`/terminal are unreachable on that path. The repo is
`$AGENTOS_REPO` (default `$PWD`); the verifier is `$AGENTOS_VERIFY` or detected
(pytest/npm/unittest), and no verifier means `not_dispatched`, never a Hermes fallback.
The task id is stable per repo+request (`$AGENTOS_TASK_ID` overrides), so a rerun resumes.
All other requests reach Hermes unchanged. The `agent-os-orchestrate` skill remains
as guidance for Hermes sessions started outside the wrapper.

A bare `hermes chat` is non-canonical: it still works, but it skips the gate, so
preload depends on model-driven skill selection and is not guaranteed.
`agentos health` reports `hermes.canonical_entrypoint`, `hermes.bare_invocations`
(any bare invocation left in Agent OS scripts/docs) and a standing INFO note;
`evals/test_canonical_entrypoint.py` fails if Agent OS files regress to bare calls.
Making the wrapper unavoidable would require changing Hermes or user-level
`~/.hermes/config.yaml`; that is deliberately not done here.
