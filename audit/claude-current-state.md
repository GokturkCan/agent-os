# Claude Code / Agent OS — Current State Audit (Read-Only)

**Date:** 2026-09-15
**Host:** macOS (Darwin 25.6.0), Apple Silicon (`/opt/homebrew` present)
**Scope:** Read-only inspection. Nothing was installed, updated, deleted, or reconfigured. No MCP server was authenticated. No credential values are printed below.

---

## 1. Claude Code Core

| Item | Value |
|---|---|
| Version | `2.1.236` |
| Binary | `/opt/homebrew/bin/claude` → symlink → `/opt/homebrew/Caskroom/claude-code/2.1.236/claude` (Homebrew Cask install) |
| Install method | Homebrew Cask (`claude-code`) |
| User config (`~/.claude.json`) | `~/.claude.json` (61 KB, contains `mcpServers`, `projects`, telemetry — no secret values inspected) |
| Global settings | `~/.claude/settings.json` |
| Local overrides | `~/.claude/settings.local.json` (permissions only: `WebSearch` allowed) |
| Data root | `~/.claude/` (366 MB total, see §6) |
| Current session model | `sonnet` (per `settings.json`) |

### Authentication mode
- Active mode: **Claude subscription / OAuth login**, evidenced by a macOS Keychain entry named `"Claude Code-credentials"` and the session's own `/login` → `Login successful`.
- No `ANTHROPIC_API_KEY` in the environment (checked existence only).
- No `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` currently active in `~/.claude/settings.json`.
- **However**, two dormant files hold a leftover **third-party API proxy credential** (see §3 "routing/model-provider" and §7 findings) — not in use today but present in plaintext on disk.

### CLAUDE.md files found
| Path | Scope | Note |
|---|---|---|
| `~/Desktop/<unrelated-project>/CLAUDE.md` | Project-local (105 lines) | Only affects that project directory |
| `/opt/homebrew/CLAUDE.md` | Homebrew repo-local | Single line: `@AGENTS.md` (imports `/opt/homebrew/AGENTS.md`, Homebrew's own contributor instructions — scoped to that repo, not the user) |
| `~/.claude/CLAUDE.md` (true global) | **Not present** | No user-wide global CLAUDE.md exists |

No global (`~/.claude/CLAUDE.md`) instruction file exists today — any "global behavior" currently comes only from plugins/skills, not a standing CLAUDE.md.

### Hooks
- `~/.claude/hooks/` — **empty directory**.
- A `SessionStart` hook is nonetheless firing (seen live this session: the "REMEMBER" buffer-status hook and a `[19:06 +03 — <user>]` UserPromptSubmit hook). These are supplied by the **`remember`** plugin, not by `~/.claude/hooks/`. No hook definitions were found under user-level `~/.claude/settings.json` (`hooks` key absent from the file as read).

### Plugins (`enabledPlugins` in `settings.json`, marketplace `claude-plugins-official` unless noted)
```
superpowers, pyright-lsp, remember, playwright, skill-creator,
notion, obsidian (marketplace: obsidian-skills / kepano/obsidian-skills),
github, postman, security-guidance, jdtls-lsp, clangd-lsp,
rust-analyzer-lsp, gopls-lsp
```
Plugin data root: `~/.claude/plugins/` (16 MB) — `installed_plugins.json`, `known_marketplaces.json`, `cache/`, `marketplaces/`, `data/`.

### Skills
Two distinct skill sources are active simultaneously:
1. **Plugin-provided skills** — namespaced, e.g. `superpowers:*` (brainstorming, systematic-debugging, TDD, writing-plans, etc.), `remember:*`, `obsidian:*`, `skill-creator:*`.
2. **`~/.claude/skills/` (93 entries)** — every entry is a **symlink into `~/.orchestra/skills/...`**, e.g. `academic-plotting -> ~/.orchestra/skills/20-ml-paper-writing/academic-plotting`. This is the **orchestra-research skill pack** (ML/RL/research-infra skills: vllm, deepspeed, peft, unsloth, langchain, dspy, etc., plus `0-autoresearch-skill`).
   - Source root: `~/.orchestra/` (contains `.lock.json` + `skills/` — not a git checkout; no `.git` dir, no remote found).
3. **SuperClaude command set** — `~/.claude/commands/sc/*.md` (33 files: `sc:analyze`, `sc:brainstorm`, `sc:implement`, `sc:load`, `sc:pm`, etc.). This is slash-command style, not the `skills/` mechanism.

### MCP servers (`claude mcp list`)
| Server | Transport | Status |
|---|---|---|
| `serena` | `uvx --from git+https://github.com/oraios/serena ...` | ✔ Connected |
| `context7` | `npx -y @upstash/context7-mcp` | ✔ Connected |
| `sequential-thinking` | `npx -y @modelcontextprotocol/server-sequential-thinking` | ✔ Connected |
| `plugin:playwright:playwright` | `npx @playwright/mcp@latest` | ✔ Connected |
| `plugin:Notion:notion` | HTTP `mcp.notion.com` | ✔ Connected |
| `plugin:github:github` | HTTP `api.githubcopilot.com/mcp/` | ✘ **Failed — HTTP 401 unauthorized** (configured Authorization header is stale/invalid) |
| `plugin:postman:postman` | HTTP `mcp.postman.com` | ⚠ **Needs authentication** |
| `claude.ai Stitch` | HTTP `stitch.googleapis.com/mcp` | ⚠ **Needs authentication** |
| `claude.ai Slack` | HTTP `mcp.slack.com` | ✔ Connected |
| `claude.ai Lovable` | HTTP `mcp.lovable.dev` | ✔ Connected |
| `claude.ai Magnific` | HTTP `mcp.magnific.com` | ✔ Connected |
| `claude.ai Higgsfield` | HTTP `mcp.higgsfield.ai/mcp` | ✔ Connected |
| `claude.ai Google Drive` | HTTP `drivemcp.googleapis.com` | ✔ Connected |
| `claude.ai Google Calendar` | HTTP `calendarmcp.googleapis.com` | ✔ Connected |
| `claude.ai Gmail` | HTTP `gmailmcp.googleapis.com` | ✔ Connected |

**MCP servers currently needing authentication: `github` (broken token, 401), `postman`, `claude.ai Stitch`.**

User-level `mcpServers` block in `~/.claude.json` explicitly configures only: `sequential-thinking`, `context7`, `serena`. The rest are plugin-registered or claude.ai account connectors.

A tool-health probe also logged: `[mcp-sdk] SEP-2352: stored OAuth credential has no 'issuer' stamp` — informational, indicates at least one stored OAuth credential predates an SDK field; not a functional error today but worth noting for future SDK upgrades.

---

## 2. Specific Component Check

| Component | Status | Evidence |
|---|---|---|
| **Superpowers** | ✅ Installed & enabled | Plugin `superpowers@claude-plugins-official: true`; skills `superpowers:*` active (brainstorming, systematic-debugging, TDD, writing-plans, code-review workflow, git-worktree helpers, etc.) |
| **SuperClaude** | ✅ Installed (two surfaces) | (a) CLI: `~/.local/bin/superclaude`, pipx venv at `~/.local/pipx/venvs/superclaude`; (b) Claude Code commands: `~/.claude/commands/sc/*.md` (33 `sc:` slash commands — analyze, brainstorm, implement, load, pm, spec-panel, business-panel, etc.) |
| **orchestra-research / AI-research-SKILLs** | ✅ Installed | `~/.orchestra/skills/` (93 skills), symlinked wholesale into `~/.claude/skills/`. No `.git` remote found locally, so provenance is inferred from skill-pack contents/naming, not a verified git origin. |
| **Serena** | ✅ Installed & connected | MCP server `serena`, launched via `uvx --from git+https://github.com/oraios/serena serena start-mcp-server ...`; connected in `claude mcp list` |
| **GitHub MCP** | ⚠️ Installed but broken | `plugin:github:github` → HTTP 401, stale/invalid Authorization header; OAuth fallback is disabled because a static header is configured |
| **Context7** | ✅ Installed & connected | `context7` MCP via `npx -y @upstash/context7-mcp`, registered in `~/.claude.json` |
| **Playwright MCP** | ✅ Installed & connected | `plugin:playwright:playwright` via `npx @playwright/mcp@latest` |
| **Memory MCP (dedicated server)** | ❌ Not present | No `@modelcontextprotocol/server-memory` or similar in `claude mcp list`. Memory-like behavior instead comes from the **`remember`** plugin (file-based, hook-driven: `~/.remember/` and `~/agent-stack/.remember/`, `now.md`/`recent.md`/`archive.md`/`core-memories.md` pattern) — a plugin, not an MCP server. |
| **Obsidian MCP** | ❌ Not present as MCP | No Obsidian MCP server in `claude mcp list`. Only an **`obsidian` plugin** (skills: `obsidian:defuddle`, `obsidian:json-canvas`, `obsidian:obsidian-bases`, `obsidian:obsidian-cli`, `obsidian:obsidian-markdown`) from marketplace `obsidian-skills` (`github:kepano/obsidian-skills`). Separately, real Obsidian vaults exist on disk (`~/Documents/ObsidianVault`, `~/Downloads/obsidian-vault`, `~/Downloads/nemotian_obsidian_vault`, plus the Obsidian.app itself) but nothing wires them to an MCP server today. |
| **Routing / model-provider extensions** | ⚠️ Dormant leftover only | No active routing today (current `settings.json` has no `env` override; Anthropic OAuth is the live path). But `~/.claude/settings.json.glm-backup` and `~/.claude/settings.jsonN` both contain a **z.ai (GLM/Zhipu) proxy config** — `ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic` plus an `ANTHROPIC_AUTH_TOKEN` **stored in plaintext**. This is not wired into the live `settings.json` but sits on disk. See §7. |

---

## 3. Duplication / Instruction-Conflict Surface (reported, not resolved)

These are **areas of overlap only** — no changes made.

1. **Slash-command duplication: Superpowers vs. SuperClaude**
   - Both ecosystems offer overlapping conceptual commands for the same intents:
     - Brainstorming: `superpowers:brainstorming` vs `sc:brainstorm`
     - Analysis/review: `superpowers:systematic-debugging`, `superpowers:requesting-code-review` vs `sc:analyze`, `sc:troubleshoot`
     - Implementation/execution: `superpowers:executing-plans`, `superpowers:subagent-driven-development` vs `sc:implement`, `sc:build`, `sc:task`, `sc:spawn`
     - Planning: `superpowers:writing-plans` vs `sc:workflow`, `sc:estimate`
   - Both frameworks also carry their **own opinions about process order** (Superpowers: "process skill before implementation skill, brainstorming before plan mode"; SuperClaude: its own command dispatcher `sc:sc`). Running both leaves it ambiguous which "process authority" wins for a given request.

2. **Skill namespace collision risk: orchestra-research pack vs. everything else**
   - The 93 orchestra-research skills are **unnamespaced** at the top level (`vllm`, `unsloth`, `deepspeed`, `langchain`, …) whereas Superpowers/other plugin skills are namespaced (`superpowers:vllm` doesn't exist, but the pattern differs enough that a future plugin adding a skill literally named `vllm` or `langchain` would collide with the orchestra pack silently, since orchestra's skills aren't prefixed).

3. **Memory system duplication: `remember` plugin vs. Serena memory vs. no dedicated memory MCP**
   - `remember` plugin: file-based session memory under `~/.remember/` (global) **and** `~/agent-stack/.remember/` (project-local) — two active memory stores for potentially the same facts.
   - `serena` also exposes its own memory tools (`mcp__serena__write_memory`, `read_memory`, `list_memories`, etc.) — a **third**, project-scoped memory mechanism, independent of `remember`.
   - No arbitration exists between "remember"-style memory and Serena's memory — an agent could write the same fact to both, or check only one and miss the other.

4. **CLAUDE.md scope ambiguity**
   - No true global `~/.claude/CLAUDE.md` exists, so today there is no conflict at the global level — but this is itself a gap (see §7 MISSING) once a "Second Brain" global instruction file is introduced, since Superpowers' own `using-superpowers` skill explicitly states "User instructions (CLAUDE.md...) take precedence over skills" — meaning a future global CLAUDE.md will need to be written knowing it *overrides* Superpowers/SuperClaude/orchestra guidance, not merge with it.

5. **Obsidian: plugin skills vs. real vaults vs. no MCP**
   - Three real Obsidian vaults exist on disk, the `obsidian` plugin provides *skills* for markdown/canvas/CLI/basing conventions, but there is no MCP server actually connecting Claude Code to a live vault — any future Obsidian MCP install will need to pick which vault is authoritative among the three found.

No attempt was made to resolve any of the above; this section is inventory only.

---

## 4. Local Prerequisite Inventory

| Tool | Path | Version |
|---|---|---|
| git | `/opt/homebrew/bin/git` | 2.51.1 |
| gh | `/opt/homebrew/bin/gh` | 2.97.0 (2026-07-31) |
| uv | `/opt/homebrew/bin/uv` | 0.8.4 (Homebrew) |
| python3 | `/opt/homebrew/bin/python3` | 3.14.2 |
| node | `/opt/homebrew/bin/node` | v25.4.0 |
| npm | `/opt/homebrew/bin/npm` | 11.7.0 |
| npx | `/opt/homebrew/bin/npx` | 11.7.0 |
| docker | `/usr/local/bin/docker` | 28.1.1 (build 4eba377) — **daemon not running** (`Cannot connect to the Docker daemon at unix://~/.docker/run/docker.sock`) |
| rg (ripgrep) | shell function wrapping `~/.local/bin/claude`, falls back to real `rg` | ripgrep 14.1.1 |
| jq | `/usr/bin/jq` | jq-1.7.1-apple |
| brew | `/opt/homebrew/bin/brew` | Homebrew 7.0.1 |
| ssh | `/usr/bin/ssh` | OpenSSH_10.3p1, LibreSSL 3.3.6 |

All prerequisites present. Only actionable item: **Docker Desktop/daemon is installed but not currently running.**

---

## 5. Relevant Directories & Config Paths (inventory only, no contents dumped)

```
~/.claude/                                   # Claude Code data root
~/.claude/settings.json                      # active global settings
~/.claude/settings.local.json                # local permission overrides
~/.claude/settings.json.glm-backup           # DORMANT — contains plaintext proxy token (see §7)
~/.claude/settings.jsonN                     # DORMANT — contains plaintext proxy token (see §7)
~/.claude.json                                # user-level config incl. mcpServers, projects, telemetry
~/.claude/hooks/                              # empty
~/.claude/agents/                             # empty
~/.claude/commands/sc/                        # SuperClaude's 33 slash commands
~/.claude/plugins/                            # plugin installs, marketplaces, cache
~/.claude/plugins/installed_plugins.json
~/.claude/plugins/known_marketplaces.json
~/.claude/plugins/marketplaces/claude-plugins-official/
~/.claude/plugins/marketplaces/obsidian-skills/
~/.claude/skills/                             # 93 symlinks -> ~/.orchestra/skills/*
~/.orchestra/                                 # orchestra-research skill pack source
~/.orchestra/.lock.json
~/.orchestra/skills/
~/.remember/                                  # global "remember" memory store
~/agent-stack/.remember/                      # project-local "remember" memory store
~/.local/bin/superclaude                      # SuperClaude CLI entrypoint
~/.local/pipx/venvs/superclaude/              # SuperClaude pipx venv
~/Library/Keychains/login.keychain-db         # holds "Claude Code-credentials" entry (OAuth)
/opt/homebrew/CLAUDE.md                       # Homebrew repo's own agent file (not global)
/opt/homebrew/AGENTS.md
~/Desktop/<unrelated-project>/CLAUDE.md   # unrelated project's own CLAUDE.md
~/Documents/ObsidianVault/                    # real Obsidian vault
~/Downloads/obsidian-vault/                   # real Obsidian vault
~/Downloads/nemotron_obsidian_vault/          # real Obsidian vault
```

---

## 6. Disk Usage Relevant to AI Tooling

| Path | Size | Note |
|---|---|---|
| `~/.claude` (total) | **366 MB** | |
| `~/.claude/security/agent-sdk-venv` | **341 MB** | Dominates `~/.claude` usage — an internal Python venv used by Claude Code's built-in security-review tooling |
| `~/.claude/plugins` | 16 MB | |
| `~/.claude/projects` | 7.2 MB | session transcripts |
| `~/Library/Caches` (total) | 4.3 GB | several dirs inaccessible (Apple system caches, permission-restricted) |
| `~/Library/Caches/BraveSoftware` | 1.7 GB | browser, not AI-tooling |
| `~/Library/Caches/Homebrew` | 370 MB | package manager cache |
| `~/Library/Caches/Codex` | 45 MB | OpenAI Codex CLI cache (adjacent AI tool) |
| `~/.cache/uv` | 2.2 GB | Python package cache (uv) — large, reusable across ML skill packs |
| `~/.npm` | 1.5 GB | npm cache (covers `npx`-launched MCP servers: playwright, context7, sequential-thinking, etc.) |
| Docker | not running | `docker system df` unreachable (daemon down); cannot report image/volume usage |
| Hugging Face cache (`~/.cache/huggingface`) | **not present** | no HF cache on this machine |
| Ollama (`~/.ollama`) | **not present** | Ollama not installed / never run |
| `~/.cache/pip`, `~/.cache/torch`, `~/Library/Caches/torch`, LM Studio | **not present** | no local model-weight caches found anywhere scanned |

**Headline:** no large local model-weight caches (HF/Ollama/torch/LM Studio) exist on this machine — all current AI tooling here is CLI/agent/MCP-oriented, not local-inference-oriented. The only outsized Claude-related consumer is the bundled security-review venv (341 MB) and general dev caches (uv/npm), none of which are safe to touch under this audit's read-only constraint.

---

## 7. Classification

**KEEP**
- Claude Code 2.1.236 (Homebrew Cask), OAuth/subscription auth via Keychain
- Superpowers plugin (functioning, actively used this session)
- Serena MCP (connected)
- Context7 MCP (connected)
- Playwright MCP (connected)
- Notion, Slack, Lovable, Magnific, Higgsfield, Google Drive/Calendar/Gmail connectors (all connected)
- orchestra-research skill pack (~/.orchestra, 93 skills, functioning)
- Core prerequisites: git, gh, uv, python3, node, npm, npx, jq, brew, ssh (all present, current)

**POSSIBLE OVERLAP**
- Superpowers vs. SuperClaude command surfaces (brainstorm/analyze/implement/plan all duplicated)
- `remember` plugin memory vs. Serena memory tools (two independent, non-arbitrated memory stores)
- orchestra-research skill pack's unnamespaced skill names vs. future plugin skill names (collision risk, not yet realized)

**NEEDS VERIFICATION**
- `plugin:github:github` MCP — 401 Unauthorized, token appears stale/invalid (needs human re-auth decision; not done here per instructions)
- `plugin:postman:postman` MCP — needs authentication (not done here)
- `claude.ai Stitch` MCP — needs authentication (not done here)
- Provenance of `~/.orchestra/skills` — no git remote found locally to confirm it is literally `orchestra-research/AI-research-SKILLs` vs. a renamed/forked/manually-assembled copy; contents strongly match that project's domain but origin isn't cryptographically/git-verifiable from this machine alone
- `~/.claude/settings.json.glm-backup` and `~/.claude/settings.jsonN` — **contain a plaintext third-party API token** (`ANTHROPIC_AUTH_TOKEN` for `https://api.z.ai/api/anthropic`, a GLM/Zhipu proxy). Not active in the live config, but sitting unencrypted on disk. Flagging for human decision on rotation/deletion — **not touched, per no-delete instruction**.
- Docker Desktop installed but daemon not running — confirm whether it's needed for the Second Brain build before assuming it's available
- SEP-2352 OAuth "issuer" stamp warning from the MCP health check — likely harmless pre-upgrade artifact, but worth a human glance if any OAuth-based MCP starts behaving oddly

**MISSING**
- No dedicated Memory MCP server (e.g. `server-memory`) — only the `remember` plugin (files) and Serena's memory tools exist
- No dedicated Obsidian MCP server — only Obsidian *skills* plus unconnected local vaults
- No true global `~/.claude/CLAUDE.md` — nothing currently declares global behavior at the user level (everything today comes from plugins/skills only)

---

*End of audit. No files were created, modified, or deleted other than this report.*
