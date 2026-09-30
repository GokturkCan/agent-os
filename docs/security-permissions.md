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
| Hermes `approvals.mode: smart`, `trust_recent_files: true` | Hermes may auto-approve some actions | review against this policy |
| Codex config trusts `/Users/gokturkcan` (home) as a project | broad trust scope | narrow to project dirs |
| `omniroute`, `clawdbot` global npm packages present | unmanaged routers/bots (OmniRoute is reference-only) | uninstall if unused |

## Git / remote safety

No remote configured; agents never push/merge. `Bash(git push:*)` and
`Bash(git remote:*)` are always disallowed for Claude Code workers.
Commits are local checkpoints only; staged diffs are scanned for secret
patterns before each commit.
