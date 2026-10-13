# Rollback & Recovery

## agent-stack repository

- Pre-V1 safety tag: `pre-agent-os-v1-mac-2026-09-30` (commit `b2262ec`).
- Full rollback of V1: `git switch main` (V1 lives on branch `agent-os-v1`), or
  `git reset --hard pre-agent-os-v1-mac-2026-09-30` on the branch (destructive — discards V1 commits).
- Partial: `git revert <commit>` for a single V1 checkpoint.
- Runtime state (`state/*`) is git-ignored; delete a single task with
  `rm -r state/tasks/<id>` after reading it.

V1 did **not** modify anything outside `~/agent-stack`: Hermes, Claude, Codex,
OpenCode configs and `~/SecondBrain` are unchanged, so no external rollback is needed.

## SecondBrain

- Every canonical write is a claude-obsidian transaction with a journal and
  original-file backups in `~/SecondBrain/.vault-meta/transactions/<op>/`.
- Interrupted operation: `python3 <engine>/scripts/claude-obsidian.py transaction recover --vault ~/SecondBrain`.
- Proposals awaiting review: `state/knowledge/proposals/`; delete a proposal
  to abandon it (no vault change happens before `apply`).
- `.raw/` is create-only; nothing in V1 deletes raw evidence.
- The vault is not a git repo. Consider `claude-obsidian checkpoint <op>` (commits a
  completed operation) if you want git history there — not enabled automatically.

## Worktrees / tasks

- Stuck lease: inspect `git -C <wt> rev-parse --git-path agentos-lease.json`;
  only the holder releases it (`agentos.worktree.release`). An operator may
  delete the lease file after confirming no worker process is running.
- Abandoned worktree: `git worktree remove <path>` (refuses when dirty;
  inspect first), branch `agentos/<task_id>` keeps the work.

## Self-improvement

- Promotion = a human merge of the candidate branch. Rollback = `git revert`
  of that merge. Canary failure records `rolled_back` and nothing is merged.
- If protected files change legitimately (human-reviewed policy edit), refresh
  the manifest: `uv run agentos manifest --write`, and commit it with the change.

## Health

`./scripts/health-check.sh` (read-only). `./scripts/run-evals.sh` for the full suite.
