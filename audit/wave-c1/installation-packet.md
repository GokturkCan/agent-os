# Wave C1 — recommended installation packet (APPROVAL REQUIRED; nothing below has been applied)

Base `main` 56a1c6e · prepared 2026-10-25 · evidence: `benchmark-results.md`, `capability-matrix.md`.
Nothing has been installed, committed, pushed or activated. No protected file, global setting, Hermes/Claude/Codex/OpenCode config, or SecondBrain content was touched.

## 1. Recommendation in one paragraph

Adopt **one** capability, as a **dormant optional specialist**: the Taste Skill v2 (`design-taste-frontend`), because it is the only candidate whose output measurably diverged from the model default (directional, n = 1) and it brings a deterministic real-browser inspector. Everything else is KEEP EXISTING / DEFER / REJECT / NOT TESTED. Expected cost when used: ~2× latency, ~+78 % input tokens, ~+35 % dollars versus an unskilled redesign. It is never default and never auto-selected (0 of 4 UI skills were selected unprompted); it is dispatched only by an explicit rule.

Not recommended for adoption (see matrix): gstack, ECC, wshobson, Composio, planning-with-files, Karpathy skills (existing overlap), Matt Pocock / Addy / Vercel React / Emil / Anthropic frontend-design / ui-ux-pro-max / pinned guidelines (no measured lift over baseline; revisit if a real task regresses), Spec Kit (needs a tool install; OpenSpec exists), paid or keyed services (Refero, 21st.dev, Motion+, imagegen).

## 2. Exact upstream and pin

| Field | Value |
|---|---|
| Repository | https://github.com/Leonxlnx/taste-skill |
| Release / commit | tag `v2.1.5` · `12af471f627f866411b4bd785b19646d3672784c` (2026-10-25) |
| Licence | MIT (© 2026 Leonxlnx); `LICENSE` sha256 `4575a543ab88dad12ccea7d97e563d0bce5b448b06072e65d3264497dad326df` |
| Source folder | `skills/taste-skill/` (frontmatter name `design-taste-frontend`) |
| Subset | 36 files, 2,346,104 bytes. Manifest: `audit/wave-c1/taste-skill-subset.sha256` (sha256 of the manifest `663e8891224fecb3b176e87610992bb6493a708a3fe5eeeee53412548b3c3f90`) |
| Excluded | `scripts/assets.mjs` (network downloader for third-party images), `evals/`, `README.md`; and everything outside the folder: `install.sh` (symlink installer), `.claude-plugin/`, `.codex-plugin/`, `.agents/`, tests, sponsor assets |
| `SKILL.md` | included byte-identical (sha256 `3435ed963b15a1b6…`); it already says "No network. If `assets.mjs` reaches no source, draw the pictures" (line 517), so the exclusion degrades gracefully; the instructions that mention `assets.mjs` remain and the model will find the file absent |

## 3. Security review summary (read, not executed by me except the inspector, see below)

- Zero npm dependencies; Node ≥ 22 built-ins only. No postinstall, no installer is used.
- Only `scripts/lib/cdp.mjs` spawns a process (Chrome/Edge/Chromium, headless, throwaway profile in `TASTE_SKILL_TMP` or the OS tmp dir, random loopback debug port, no `--no-sandbox`). No `child_process` anywhere else; no `new Function`, no dynamic import of fetched data (the one dynamic import is a local file).
- Environment read: `CHROME_PATH`, `PUPPETEER_EXECUTABLE_PATH`, `HOME`, `TASTE_SKILL_HISTORY`, `TASTE_SKILL_TMP`. No secret variables.
- Writes: `.taste-skill/` in the project root (working files), temp Chrome profile, and **`~/.taste-skill/history.json`** (draw history; override with `TASTE_SKILL_HISTORY`). This is outside the worktree: see decision D4.
- `inspect.mjs` serves local files from a throwaway 127.0.0.1 server; it can also load an http(s) URL given on the command line.
- Residual risks: 39.5 KB of third-party prose is instruction text for the model (provenance pinned by hash; any bump needs re-review); an opinionated house style may fight a brand brief; command-text deny patterns are not a sandbox.
- I executed only `inspect.mjs` (after reading `cdp.mjs`, `inspect.mjs` and grepping all scripts) against local files, plus whatever the benchmark arm ran (draw/inspect/lint). `assets.mjs` was never run.

## 4. Proposed changes, split by protection

### 4a. Unprotected (can be done under one approval; leaves the skill dormant)

| Change | Detail |
|---|---|
| Vendor | `third_party/taste-skill/LICENSE` and `third_party/taste-skill/skill/…` = the 36-file subset. `third_party/` is not on any loading path, so the skill is **dormant** and invisible to hosts and Hermes. |
| Lock | `scripts/runtime/skills.lock.json`: new `taste-skill` entry (source, tag, commit, licence, installed list, excluded list, sha256 per file), same schema as `ponytail`. |
| Docs | `config/skills.yaml` (unprotected): `taste_skill` source, `status: staged`, `agent_os: optional_specialist`; `docs/wave-c1.md` (this wave's review); CHANGELOG line. |
| `.gitignore` | ignore `.taste-skill/` |
| Nothing else | no `skills/` entry, no registry change, no worker exposure |

### 4b. Protected (separate approval packet required; NOT part of this approval unless you say so)

| Protected file | Change | Why |
|---|---|---|
| `config/capability_registry.yaml` | new provider (proposed text below) | records the capability and its state truthfully (`benchmark`, not `adopted`) |
| `evals/test_wave_c1_skills.py` (new; `evals/` is protected, manifest 78→79) | asserts lock hashes, no hooks, `assets.mjs` absent, no `disable-model-invocation`, frontmatter parses, skill absent from `skills/` until activation, present after | keeps the staged skill auditable |
| `evals/protected-manifest.json` | refresh via `agentos manifest --write` only after recorded approval | established workflow |
| **No change** to `config/workers.yaml`, `permissions.yaml`, `mcp.yaml` | `coder` workers already have `Bash`; deny patterns stay | verified by reading `workers.yaml` |

Proposed registry record (for the protected packet, not applied):

```yaml
  - id: taste-skill
    kind: skill
    adoption: benchmark          # becomes adopted only after activation + acceptance
    capabilities: [ui.quality_filter]
    locality: local
    cost: free
    latency: local_slow
    risk: medium                 # runs headless Chrome, writes ~/.taste-skill unless env set
    hosts: [any]
    probe:
      - {type: path, paths: ["~/agent-stack/third_party/taste-skill/skill/SKILL.md"]}
    notes: "Staged dormant; pin v2.1.5 12af471; assets.mjs excluded; explicit-dispatch only. See scripts/runtime/skills.lock.json."
```
(`anti-slop`, also `ui.quality_filter`, stays `future`; no routing rule is added in this packet.)

### 4c. Activation — **superseded** by `protected-packet/README.md` (task-scoped delivery into the worker worktree; no copy into `skills/`)

(Original text kept for the record.)

`cp -R third_party/taste-skill/skill skills/design-taste-frontend` (the existing Agent OS loading path that Hermes reads through `external_dirs`; the same mechanism as Ponytail). Routing: dispatched only by an explicit task template ("public-facing page design"), never by description matching. Interactive Claude/Codex/OpenCode skill directories remain **unchanged**.

## 5. Acceptance tests (run at activation; none run yet for these hosts)

| Host | Test | Pass condition |
|---|---|---|
| Claude Code (verified in the benchmark, project scope) | isolated `claude -p` in a scratch repo with the skill in `.claude/skills/`; "Use the design-taste-frontend skill", build a one-page site | `Skill` tool_use recorded; `node scripts/inspect.mjs <page>` exits 0 or reports only WARN; independent checker (`bench/tools/check_ui.mjs`) shows 0 overflow / 0 contrast failures |
| Claude Code under Agent OS dispatch | `agentos dispatch` a `coder` task with the skill on the path | skill loads, `assets.mjs` absent is tolerated, no write outside the worktree except `~/.taste-skill/history.json` (or none if env set), `git push`/`gh` denied as before |
| Codex | same directory copied to a scratch `CODEX_HOME`-style skills path (not `~/.codex`) | skill listed, loadable; scripts run (node + Chrome present) — **NOT TESTED yet** |
| OpenCode | same, scratch config dir | listed, loadable — **NOT TESTED yet** |
| Hermes | visibility via the existing `external_dirs` after activation (read-only check, no Hermes config edit) | skill appears in Hermes' skill list; Hermes does **not** auto-load it for non-UI tasks — **NOT TESTED yet** |
| Antigravity | — | **UNVERIFIED** (no host available) |
| Negative | install, then run a non-UI task (debug/refactor) with natural prompts | no `Skill` call to design-taste-frontend |
| Integrity | `shasum -a 256 -c audit/wave-c1/taste-skill-subset.sha256` from the skill folder | all 36 OK; no `hooks/`, no `assets.mjs` |

## 6. Rollback

- Before activation: `git rm -r third_party/taste-skill`, remove the lock entry, revert docs/yaml (all in one commit; `git revert` suffices).
- After activation: `rm -rf skills/design-taste-frontend`; `rm -rf ~/.taste-skill .taste-skill` (history/working files only); revert registry/test commit and re-run `agentos manifest --write` under a recorded approval.
- Host-level: no host directory was changed, so there is nothing to restore there.

## 7. Approval decisions needed

| # | Decision | Recommended |
|---|---|---|
| D1 | Stage taste-skill v2.1.5 subset dormant under `third_party/` with lock + docs (section 4a)? | **YES** |
| D2 | Authorise a separate protected packet for the registry record + `evals/test_wave_c1_skills.py` + manifest refresh (4b)? | YES, as its own packet |
| D3 | `assets.mjs` excluded (recommended) or included? | exclude; revisit only with a network-policy decision |
| D4 | `~/.taste-skill/history.json` write: accept, or require a launcher that sets `TASTE_SKILL_HISTORY` to a worktree path (a wrapper like `bin/repomix`, protected-adjacent)? | accept for dormant staging; decide before activation |
| D5 | Activation (4c) and its routing rule — now or after more evidence? | after repeat runs (n ≥ 3, blind rating) |
| D6 | Fund follow-up evidence: repeat the UI arms n ≥ 3 with blind rating, run task 4 (spec → impl → review) as multi-session, harder engineering tasks, host acceptance for Codex/OpenCode/Hermes in scratch dirs? | YES (token cost only) |
| D7 | Credentialed/paid candidates (Refero Pro + MCP, 21st.dev key, Motion+ token): provide credentials through Keychain yourself, or stay NOT TESTED? Never paste them in chat. | stay NOT TESTED |
| D8 | Optional, separate: Superpowers 7.0.0 → 7.0.1 patch update; Ponytail stays pinned at v5.3.2 (upstream has moved; re-review before any bump) | separate task |
| D9 | Also stage Anthropic `frontend-design` (Apache-2.0, 9 KB, zero scripts) as a low-risk fallback? | NO (no measured lift; overlaps taste) |
