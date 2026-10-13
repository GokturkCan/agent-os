# Security & Permission Summary (V1)

## Layers

1. **Filesystem roles** — `config/permissions.yaml` (unchanged by V1): operator,
   knowledge_compiler, research_worker, reviewer; `wiki/`, `.raw/`,
   `.vault-meta/` and policy files protected.
2. **Worker capability profiles** — `config/capabilities.yaml` (new, policy-protected):
   readonly, coder, reviewer, knowledge_compiler, knowledge_reviewer (human-only), untrusted.
3. **Never-grantable** — git_push, git_remote_change, credential_change,
   permission_change, policy_change, external_publish, secrets_read,
   destructive_delete, modify_judge, modify_heldout_evals, modify_promotion_criteria.
4. **Structural enforcement at launch** — `agentos/workers.py` translates the profile
   into harness flags; nothing relies on prompt text.
5. **Knowledge gate** — canonical SecondBrain writes need proposal + engine hash +
   independent reviewer + human approval ref; engine CAS prevents silent overwrite.
6. **Protected manifest** — `evals/protected-manifest.json` pins SHA-256 of
   judges/held-out evals/policy (`agentos.permissions.PROTECTED_POLICY_PATHS`).
   Health check FAILs on drift; self-improvement candidates touching them are rejected.

## Verified (executed)

| Claim | Evidence |
|---|---|
| Readonly Claude Code worker cannot write files | live run 2026-10-01: `permission_denials=1`, fixture checkout unchanged |
| Readonly Codex worker cannot write files | live run 2026-10-01: sandbox refused `pwned.txt`, checkout unchanged |
| Profiles never hold never-grantable caps | `evals/test_a7_permissions.py`, `config.validate` |
| Escalation needs operator grant with human approval; self-issued grants refused | `test_escalation_needs_operator_grant_with_human_approval` |
| Coding workers see only context7+serena; no claude.ai connectors, no browser | `test_coding_worker_gets_no_broad_browser_or_account_connectors` |
| Canonical write refused without approval / with self-approval / on changed target | `evals/test_a1_knowledge.py` |

## Known exposures (flagged, not changed — need your decision)

| Item | Risk | Suggested action |
|---|---|---|
| Interactive Claude Code sessions (not Agent OS worker runs) see all claude.ai connectors incl. Gmail send, Slack post, Drive share, Lovable/Higgsfield publish | high-impact external side effects available ambiently | disable unused connectors at claude.ai, or keep interactive-only |
| `~/.claude/settings.json.glm-backup`, `~/.claude/settings.jsonN` hold a plaintext z.ai token (from 2026-09-15 audit) | credential at rest | rotate at z.ai, then delete the files |
| GitHub MCP static Authorization header rejected (401) | broken tool; stale token on disk | re-authenticate or remove the header config |
| Hermes default model = kimi-k3 (disabled in policy), no fallback_model | Hermes outage on NIM hiccup | set default to an approved model and add `fallback_model` |
| Hermes bundled skills `claude-code`/`codex`/`opencode` let Hermes launch workers directly (bypassing capability profiles, worktrees, budgets) | policy bypass by prompt | `skills.disabled` — part of the proposed wiring (docs/hermes-integration.md) |
| Hermes `approvals.mode: smart`, `trust_recent_files: true` | Hermes may auto-approve some actions | review against this policy |
| Codex config trusts `$HOME` (home dir) as a project | broad trust scope | narrow to project dirs |
| `omniroute`, `clawdbot` global npm packages present | unmanaged routers/bots (OmniRoute is reference-only) | uninstall if unused |

## Hermes → agentos boundary

- Workers launched by `agentos dispatch` run with `AGENTOS_WORKER_CONTEXT`; a nested
  `agentos dispatch` that inherits it is refused (`exit_state: unsafe`). This is a **cooperative
  guard, not a capability boundary**: a worker that unsets the variable is not stopped by it. The
  real limits are the profile's tool/sandbox restrictions and the push/remote controls below.
- High-risk markers stop before any side effect (`human_handoff`); an approval
  reference passed by Hermes is written to telemetry for audit.
- `--verify` runs as an argv (no shell).
- `agentos/hermes_bridge.py` never writes `~/.hermes`; only the human-run
  `scripts/hermes-wire.py apply --i-approve` does, with backup + verification + auto-restore.

## Git / remote safety

A private `origin` (`GokturkCan/agent-os`) exists; agents never push, change remotes or merge.
Push and remote rewriting are denied in two independent layers:

1. **Claude Code deny list** (`config/workers.yaml` `always_disallowed`): wildcard `Bash(*git*push*)`
   and `Bash(*git*remote*)` (the latter also covers `git config remote.*`). A live probe against a
   throwaway local remote (2026-10-14) showed the old exact-prefix patterns let `git -C . push`,
   `/path/to/git push`, `git -c k=v push`, `sh -c 'git push'` and `git --no-pager push` through; the
   wildcard patterns stopped all 13 push/remote-rewrite spellings tried. Over-blocking is intentional.
2. **Structural `pre-push` guard** (`agentos/githooks`, injected via `GIT_CONFIG_*` env into every
   enforced launch, Claude and Codex): any `git push` the worker's git sees fails, whatever the
   spelling (probe: it alone stopped every spelling the old patterns missed). It does **not** stop
   remote-config rewriting, and `git push --no-verify` / `-c core.hooksPath=` bypasses it; those are
   covered by layer 1 (Claude) or the Codex sandbox (not probed here). Repo-local git hooks do not run
   for git commands the worker itself issues (dispatch's own commit is unaffected).

`rm -rf` and `sudo` remain exact-prefix denials (best-effort). Commits are local checkpoints until a human
pushes. The coder profile also holds `mcp_playwright` (human-approved 2026-10-13) but receives Playwright
only when a capability plan selects it. No secret-scan script is committed; scanning staged diffs for
secret patterns is a manual pre-commit step.

## Worker launch enforcement

Only workers whose launch adapter enforces the capability profile are launchable
(`agentos.workers.ENFORCED_WORKERS`: `claude_code`, `codex`). Any other worker, including a
re-enabled `opencode`, is refused by `build_launch` and skipped by the router (fail closed).
OpenCode is registered but disabled until an adapter exists that gives it a sandbox/tool allowlist
and a strict MCP set.
