# adapters/ — bridges to external systems

Adapters live as small modules in `agentos/` rather than a plugin framework.

| External system | Adapter | Status |
|---|---|---|
| claude-obsidian engine (SecondBrain) | `agentos/knowledge.py` (drives `claude-obsidian.py` capture/transaction/lint/doctor) | IMPLEMENTED, VERIFIED |
| Claude Code CLI | `agentos/workers.py` (`claude -p --strict-mcp-config ...`) | IMPLEMENTED, VERIFIED live |
| Codex CLI | `agentos/workers.py` (`codex exec --sandbox ...`) | IMPLEMENTED, VERIFIED live (read-only) |
| OpenCode CLI | `agentos/workers.py` (`opencode run`) | IMPLEMENTED (argv only), not run |
| DeepSeek Harness | `~/run_deepseek_harness_nim.py` (outside repo) | MEASURED separately; no agentos launch adapter |
| Hermes | read-only inspection in `agentos/health.py` | PARTIAL — Hermes does not yet call `agentos` |
| MSI | `agentos/resources.py` (ssh probe, profile state machine) | IMPLEMENTED; node unreachable today |
| Research subsystems | contract in `workflows/research-question.md` | DESIGN-ONLY |

## Hermes integration (next step, needs your approval)

Hermes already has `terminal` + `skills` toolsets. The minimal integration is
to expose `skills/agent-os-task/SKILL.md` to Hermes (symlink into
`~/.hermes/skills/`) so Hermes runs `uv run agentos route|task|health` from
`~/agent-stack`. That modifies Hermes' user config, so it was not done
automatically.
