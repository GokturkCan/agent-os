# Taste Skill (vendored, DORMANT)

- Upstream: https://github.com/Leonxlnx/taste-skill — tag `v2.1.5`, commit `12af471f627f866411b4bd785b19646d3672784c` (2026-10-25)
- Licence: MIT, © 2026 Leonxlnx (`LICENSE`, sha256 `4575a543ab88dad12ccea7d97e563d0bce5b448b06072e65d3264497dad326df`)
- Source folder: `skills/taste-skill/` (frontmatter name `design-taste-frontend`)
- Included: the reviewed 36-file subset (`SHA256SUMS`, paths relative to `skill/`). Byte-identical to upstream; nothing edited.
- Excluded on purpose: `scripts/assets.mjs` (network image downloader), `evals/`, upstream `README.md`, and everything outside the folder (`install.sh`, plugin manifests, tests, sponsor assets).
- Status: **dormant**. Not under `skills/`, no registry record, no worker exposure. Activation needs a separate approval (audit/wave-c1/installation-packet.md §4c).
- Verify: `uv run python scripts/verify_skills_lock.py` (also checks the lock in scripts/runtime/skills.lock.json).
- Rollback: `git rm -r third_party/taste-skill`, delete the `taste-skill` entry in `scripts/runtime/skills.lock.json` and the `taste_skill` source in `config/skills.yaml`.
- Runtime notes (from review): Node >= 22 and an installed Chrome/Edge/Chromium; writes `.taste-skill/` in the project and `~/.taste-skill/history.json` unless `TASTE_SKILL_HISTORY` is set; headless Chrome is the only spawned process.
