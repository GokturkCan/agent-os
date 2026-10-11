# Security

Agent OS V1 is a private, solo-maintained project. These are the rules the repo follows.

## Secrets

- Credentials are **environment variables or the provider CLI's own login/keychain** —
  never files in this repo. `config/*.yaml` records *where* a credential lives, not its value.
- `.env` and variants are git-ignored; `.env.example` holds names only.
- Do not paste keys into prompts, tasks, issues, commit messages or audit notes.
- Telemetry/events redact secret-looking strings and never store prompts or worker output,
  but treat that as defense in depth, not a guarantee.
- If a key is ever committed or exposed: revoke/rotate it at the provider first, then clean
  history.

## Runtime state

`state/` (tasks, worktrees, telemetry, events, approvals), logs, caches, local model weights
and raw provider/session evidence are git-ignored and must not be committed. Audit notes
committed to `audit/` are sanitized summaries (no raw transcripts, no credentials; use `~`
and `<tmp>` instead of machine-specific absolute paths).

## Execution boundaries

Workers run in per-task git worktrees under capability profiles (strict MCP, tool
allow/deny lists, sandbox). `git push`, `git remote`, `rm -rf` and `sudo` are denied;
permission-bypass flags are rejected. Protected files (`evals/protected-manifest.json`) need
review to change. Canonical SecondBrain writes go through a reviewed gate.

## Reporting

While the repository is private and solo-maintained, record issues in the repo owner's own
tracker or notes. Issue/trace/log artifacts must contain **no credentials or personal data**;
redact before attaching. If the repository is ever shared or made public, add a private
contact channel here before doing so.
