# Candidate Adoption Table (2026-10-01)

Decision rule: adopt only on a real capability gap, not covered by existing
tools, measurable benefit, acceptable context/security/maintenance cost, no
competing control plane.

| Candidate | Decision | Rationale |
|---|---|---|
| Hermes | ADOPTED (orchestrator) | installed v0.21.3; memory disabled as required |
| claude-obsidian 2.2.0 | ADOPTED | already installed; transaction/CAS/lint engine reused instead of writing one |
| Claude Code | ADOPTED (primary worker) | verified live via agentos launch |
| Codex | ADOPTED (primary/reviewer worker) | verified live (read-only sandbox) |
| DeepSeek Harness + v4.1-flash (NIM) | ADOPTED (background escalation) | prior benchmark `audit/nvidia-nim-2026-09-24.md` |
| Superpowers | ADOPTED | installed; engineering process SOP |
| Serena | ADOPTED | connected; exposed to coder/readonly profiles |
| Context7 | ADOPTED | connected; developer_docs route |
| Playwright MCP | ADOPTED (task-specific) | connected; only for deterministic_browser needs |
| Anthropic SKILL.md packaging | ADOPTED | `skills/agent-os-task/SKILL.md` |
| GitHub MCP (restricted toolsets) | ADOPTED, BLOCKED | 401 — needs human re-auth; gh CLI read-only fallback |
| OpenCode | ADOPTED (optional overflow) | installed; GSD pack disabled by policy |
| Ponytail | BENCHMARK / not installed | intent captured as policy text in `docs/v1-implementation.md` §6 |
| codebase-memory-mcp | BENCHMARK | derived structural index; freshness contract ready (`worktree.index_stamp`) |
| Repomix | BENCHMARK (on demand) | `npx repomix` when repo packing is needed; no standing install |
| Laya-MLX (FastGate) | BENCHMARK (operationally measured 2026-10-14; decision quality unmeasured; not a default) | selectable explicitly via `config/systemone.yaml`; evidence `audit/laya-mlx-r3.2-2026-10-14.md` |
| Qwen3.6-35B-A3B (MSI) | BENCHMARK | needs MSI connection + benchmark |
| Bonsai 2 (Mac) | BENCHMARK | needs runtime + RAM check on 16 GB |
| Firecrawl | DEFERRED | no key; web_fetch covers current need |
| Crawl4AI | DEFERRED | no local/private crawl need yet |
| MarkItDown | DEFERRED | claude-obsidian capture covers md/txt/pdf today |
| RTK | DEFERRED | no measured gap |
| Claude HUD | DEFERRED | UI nicety; not V1-critical |
| n8n | DEFERRED | no stabilized workflow needs a deterministic engine yet |
| browser-use | DEFERRED | Playwright covers deterministic needs |
| Scrapling | DEFERRED | fallback only on demonstrated hard scraping |
| Prime / OpenMausBot / Graphify / media tools | DEFERRED | specialist, on demand |
| DeepSeek direct / GLM | DEFERRED | no key configured; cloud chain covered by subscriptions |
| HarnessRouter | REFERENCE | agentos/workers.py covers V1 launch normalization |
| Archon, OmniRoute, Graft, Headroom | REFERENCE | no gap; OmniRoute npm install present but unused |
| sequential-thinking MCP | NOT EXPOSED to workers | no measured value |
| SuperClaude, OpenCode GSD | REJECTED for Agent OS tasks | overlapping planning frameworks (left installed) |
| Vector/graph/memory DBs (Mem0, Graphiti, Qdrant, Neo4j, ...) | REJECTED for V1 | no measured gap; SecondBrain is canonical |
| kimi-k3 on NIM | REJECTED | 0-byte responses (`audit/nvidia-nim-2026-09-23.md`) |
