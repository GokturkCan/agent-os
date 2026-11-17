# Project inspect, onboarding and continuation

Read-only repository inspection and Agent OS–grounded continuity. Canonical SecondBrain
writes still require the existing human-reviewed claude-obsidian gate.

## CLI

All commands: `~/agent-stack/bin/agentos knowledge …`

| Command | Purpose |
|---------|---------|
| `inspect --repo <path>` | Collect bounded Markdown sources, git HEAD/dirty, identity candidate |
| `onboard --repo <path> --authorized` | Stage a DRAFT `kind: project` proposal (requires explicit flag) |
| `status --project <id> --repo <path>` | Task/lease/git/proposal status with provenance labels |
| `continue --project <id> --repo <path> --objective "…"` | Bounded continuation package (no auto-dispatch) |

Existing lifecycle commands (`capture`, `context`, `dispatch`, `list`, …) are unchanged.

## Provenance labels

- **VERIFIED FROM AGENT OS** — durable task state, leases, dispatch outcomes
- **VERIFIED FROM GIT** — `git rev-parse` / `status --porcelain`
- **DOCUMENTED IN MARKDOWN** — excerpts from repo files (untrusted data)
- **APPROVED SECOND BRAIN KNOWLEDGE** — reviewed vault notes via `context`
- **UNKNOWN** — no authoritative record

## First real project

1. `knowledge inspect --repo /path/to/your/repo`
2. Resolve `canonical_match` (missing/ambiguous/matched)
3. Prepare onboarding: `knowledge onboard --repo … --authorized` (or manual `capture` JSON)
4. `ready` → `export` → existing reviewer workflow → `reconcile`
5. `knowledge status --project <id> --repo …`
6. `knowledge continue --project <id> --repo … --objective "…"`

## Limitations

- Repo must be a local git worktree; Markdown only; no script execution from README content
- Task association uses repo path appearing in task goal/checkout (deterministic string match)
- Worker identity after task close falls back to lifecycle `outcomes/*.json` when task owner was cleared
- `continue` never calls `--execute` on dispatch; active leases block auto-resume posture
