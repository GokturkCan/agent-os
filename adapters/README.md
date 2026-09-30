# adapters/ — bridges to external systems

Adapters live as small modules in `agentos/` rather than a plugin framework.

| External system | Adapter | Status |
|---|---|---|
| claude-obsidian engine (SecondBrain) | `agentos/knowledge.py` (drives `claude-obsidian.py` capture/transaction/lint/doctor) | IMPLEMENTED, VERIFIED |
| Claude Code CLI | `agentos/workers.py` (`claude -p --strict-mcp-config ...`) | IMPLEMENTED, VERIFIED live |
| Codex CLI | `agentos/workers.py` (`codex exec --sandbox ...`) | IMPLEMENTED, VERIFIED live (read-only) |
| OpenCode CLI | `agentos/workers.py` (`opencode run`) | IMPLEMENTED (argv only), not run |
| DeepSeek Harness | `~/run_deepseek_harness_nim.py` (outside repo) | MEASURED separately; no agentos launch adapter |
| Hermes | `agentos/hermes_bridge.py` (read-only probes), `skills/agent-os-orchestrate`, `bin/agentos`, `agentos dispatch` | IMPLEMENTED, VERIFIED in sandbox HERMES_HOME; live wiring awaits approval |
| MSI | `agentos/resources.py` (ssh probe, profile state machine) | IMPLEMENTED; node unreachable today |
| Research subsystems | contract in `workflows/research-question.md` | DESIGN-ONLY |

## Hermes integration

See `docs/hermes-integration.md` (approval boundary, exact diff, rollback, post-change tests).
