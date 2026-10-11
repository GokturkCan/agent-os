# Hermes / Groq milestone — 2026-10-01

## Measured native completion

Hermes 0.21.3 native `resolve_runtime_provider` -> `AIAgent.run_conversation`,
using a disposable HERMES_HOME, existing Groq credential reference, no tools,
skills, project files, memory or conversation history. No live config change
was made to perform the probe.

- Requested provider: `groq-gpt-oss-120b`; runtime provider: `custom`.
- Model: `openai/gpt-oss-120b`.
- Endpoint: `https://api.groq.com/openai/v1/chat/completions`.
- Prompt: `Reply with exactly OK.`
- Request: 2,021 bytes; system 1,771 characters, user 22 characters; zero tools.
- Hermes resolved context window: 131,072 tokens; output cap: 256 tokens.
- One API call; HTTP 200; final response `OK`; completed true, failed false.
- Total elapsed: 1.273 seconds; HTTP/stream elapsed: 0.272 seconds.
- Local evidence: `<tmp>/agentos-groq-clean-20261001/attempt1/report.json`.
- Repro command: `~/.hermes/hermes-agent/venv/bin/python <tmp>/agentos-groq-clean-20261001/probe.py attempt1`.

The earlier Claude probe used NVIDIA, confirmed by the saved request URL, and
its HTTP 410 is not evidence about Groq. The subsequent explicit Groq oneshot
reported context overflow; no raw error dump was persisted. Its database
contains only the new user message, not old conversation history. Exact cause
of that error remains under investigation; it does not establish provider failure.

## Live primary

After success, backed up the live config byte-for-byte to
`~/.hermes/config.yaml.backup-before-groq-20261001T020909Z`, verifying its SHA-256
against the original baseline before writing. Only default, provider and
base_url changed; api_mode was already chat_completions. No fallback added.
Memory, skills, MCP settings, credentials and comments preserved.

Groq's measured state is limited to authenticated native connectivity; general
coding/orchestration quality has not yet been established. Worker routing is
unchanged. Kimi remains disabled and NVIDIA remains background-only.

## Context-error diagnosis

The default live Hermes request reproduced the misleading context message.
Captured Groq response: HTTP 413, `rate_limit_exceeded`, tokens-per-minute
limit 8,000, requested 8,451. This is an account TPM ceiling, not the model's
131,072-token context window. Hermes' overflow recovery replaces this provider
error with a generic compression-disabled message. The original explicit
probe's exact request count was not preserved, so the reproduction establishes
the failure mechanism, not its precise original token count.

The reproduced request was 38,994 bytes: one 16,934-character system message,
one 386-character user message, and 13 tool schemas; no conversation history.
The default toolset and system/skill instructions are enough to exceed the
account's per-request TPM ceiling. No evidence supports corrupt model metadata.

Using `-t skills,terminal` reduces this to seven tool schemas and ~27.7 KB;
Groq accepts individual requests but subsequent turns incur HTTP 429 TPM waits.
No account upgrade, extra credential, compression change or fallback was made.

## Validation

- Agent OS health: 25 checks, 0 FAIL, 3 WARN (fallback unset, GitHub MCP, Postman).
- Integration tests: 19 passed, 1 live-only skipped.
- Full suite: 77 passed, 2 live-only skipped; protected manifest intact.
- Hermes doctor run without --fix or --live: custom-provider vendor-slug warning
  is inconsistent with the measured successful exact model ID; existing npm
  vulnerability reports are 3 agent-browser, 9 web workspace, 4 ui-tui workspace.
  Optional integration warnings remain; no packages or credentials changed.

## E2E observations in progress

The default-toolset attempt failed before tools with the HTTP 413 above.
The scoped attempt loaded no Agent OS skill before inspecting fixture files;
it was stopped while read-only. Skill discovery was confirmed working, but
its 60-character index description only said "Dispatch coding work...".
The integration skill now makes mandatory use explicit in its discovery
summary and reduces loaded instructions while preserving safety requirements.

## Real dispatch reached Claude, blocked by subscription quota

Hermes native skill preload (`--skills agent-os-orchestrate`) in a disposable
home made the required dispatch path concrete. Native skill discovery alone
did not reliably select the skill; it is not accepted as unattended routing.

- Hermes session: `20261001_051741_5593be`.
- Task: `hermes-inclusive-20261001`.
- Agent OS runs: `run-20261001T021831-008927`, `run-20261001T021923-8a6572`.
- Worker runs: `run-20261001T021831-d9cd56`, `run-20261001T021923-5e4aff`.
- Worker: `claude_code`, provider `claude_subscription`, profile `coder`.
- Worktree: `state/worktrees/agentos-hermes-fixture-20261001-hermes-inclusive-20261001`.
- Task branch: `agentos/hermes-inclusive-20261001`; no successful commit.
- Original fixture: `<tmp>/agentos-hermes-fixture-20261001`, clean `main`,
  HEAD `228309b2b12d3e04a74d904ddd22a38ca2e3b252` unchanged.
- Verification: `python3 -m unittest -v`, four tests, three failing.
- Claude session `caddc543-fbf9-4055-b4d5-2efe2bce486d` reports:
  "You've hit your session limit · resets 6:50am (Europe/Istanbul)".
- Hermes received the retryable result and retried the SAME task id; both
  attempts used the same worktree, accumulated state and released their leases.
  Automatic retries were stopped before the final available attempt was spent.
- No direct-worker skill or direct worker launch occurred in the captured
  Hermes dispatch transcript. Claude was launched by Agent OS, under strict
  MCP configuration and the original coder capability profile.

This demonstrates failed-task persistence and a real worker launch, but does
NOT satisfy successful E2E or fail-then-success acceptance. No tests were
weakened, no budgets reset, no quota/billing/login change, and no alternate
worker substituted. A separate disposable first-verification-failure fixture
has been prepared but not run while Claude is unavailable.

Supporting evidence (native probe, Hermes tool transcript, dispatch telemetry,
persisted task-state snapshot) was captured locally under
`audit/hermes-groq-2026-10-01/`. That directory is **git-ignored** (raw
provider/session output; may contain local paths and session identifiers) and is
not part of the repository. This document is the sanitized, committed summary.
Local paths above use `<tmp>` / `~` placeholders for portability.
