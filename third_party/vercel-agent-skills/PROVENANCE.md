# Vercel skills (vendored, DORMANT)

- Upstream: https://github.com/vercel-labs/agent-skills — commit `063bee94c3f4df8453406c830b0a7df0f2860278` (staged 2026-10-26)
- Licence: MIT per upstream README and SKILL.md frontmatter (see note)
- Modules staged: `react-best-practices` (frontmatter name `vercel-react-best-practices`) and `composition-patterns`. 82 files, byte-identical to upstream; nothing edited. Hashes: `scripts/runtime/skills.lock.json`.
- Excluded on purpose: AGENTS.md (compiled duplicate), README.md (pnpm build), metadata.json, rules/_template.md, react-best-practices.zip, packages/, scripts/, web-design-guidelines and every other skill
- Status: **dormant**. Not under `skills/`, no registry record, no worker exposure, no hooks, no scripts. Activation needs a separate approval.
- Note: **No LICENSE file exists upstream** at this commit. The only licence statements are the upstream README (`## License: MIT`) and `license: MIT` in the vendored SKILL.md frontmatter; no copyright holder is named. Owner should accept or request a clarification upstream before activation. SKILL.md files still mention the excluded compiled `AGENTS.md`; the `rules/` files carry the same content.
- Verify: `uv run python scripts/verify_skills_lock.py`
- Rollback: `git rm -r third_party/vercel-agent-skills`, delete the `vercel-agent-skills` entry in `scripts/runtime/skills.lock.json` and its source in `config/skills.yaml`.
