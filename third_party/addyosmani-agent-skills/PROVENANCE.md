# Addy Osmani skills (vendored, DORMANT)

- Upstream: https://github.com/addyosmani/agent-skills — tag `0.6.13`, commit `aeac41d4d005999432bb7312f7ff06383a91d59d` (staged 2026-10-26)
- Licence: MIT, `LICENSE` sha256 `6f202f8bd568cd730dbb2b0d1f8e243bc74c2fa1f64dbce9b2c7ea08bd5c9fd7`
- Modules staged: `api-and-interface-design`, `security-and-hardening`, `observability-and-instrumentation`, `ci-cd-and-automation`, `deprecation-and-migration`. 8 files, byte-identical to upstream; nothing edited. Hashes: `scripts/runtime/skills.lock.json`.
- Excluded on purpose: hooks/, agents/, commands/, scripts/, plugin.json, evals/, docs/, all other 20 skills
- Status: **dormant**. Not under `skills/`, no registry record, no worker exposure, no hooks, no scripts. Activation needs a separate approval.
- Note: Upstream paths are mirrored (`skills/<name>/`, `references/`) because SKILL.md files link `../../references/*-checklist.md`. Example snippets inside the skills mention `npx`/CI commands; they are documentation, never executed by Agent OS. The `hooks/` directory is not staged.
- Verify: `uv run python scripts/verify_skills_lock.py`
- Rollback: `git rm -r third_party/addyosmani-agent-skills`, delete the `addyosmani-agent-skills` entry in `scripts/runtime/skills.lock.json` and its source in `config/skills.yaml`.
