# Matt Pocock skills (vendored, DORMANT)

- Upstream: https://github.com/mattpocock/skills — commit `5beb35b040e3de97e54fa9e386d7e42d15c295c2` (staged 2026-10-26)
- Licence: MIT, `LICENSE` sha256 `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5`
- Modules staged: `codebase-design` (SKILL.md frontmatter name `codebase-design`). 3 files, byte-identical to upstream; nothing edited. Hashes: `scripts/runtime/skills.lock.json`.
- Excluded on purpose: agents/openai.yaml, every other skill (incl. migrate-to-shoehorn, setup-ts-deep-modules: no demonstrated utility), README, scripts, plugin manifests
- Status: **dormant**. Not under `skills/`, no registry record, no worker exposure, no hooks, no scripts. Activation needs a separate approval.
- Note: No demonstrated utility yet: `migrate-to-shoehorn` and the in-progress TypeScript skills were not staged.
- Verify: `uv run python scripts/verify_skills_lock.py`
- Rollback: `git rm -r third_party/mattpocock-skills`, delete the `mattpocock-skills` entry in `scripts/runtime/skills.lock.json` and its source in `config/skills.yaml`.
