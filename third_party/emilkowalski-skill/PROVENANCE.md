# Emil Kowalski skills (vendored, DORMANT)

- Upstream: https://github.com/emilkowalski/skill — commit `2d228630ba1446365f614a108cb8252f1feda202` (staged 2026-10-26)
- Licence: MIT, `LICENSE` sha256 `4ff5bdb7887ec1435c9cab0e8d1a7caee704d894d65c2a008ccc68b1cc2f260b`
- Modules staged: `animation-performance` and `break-ui`. 3 files, byte-identical to upstream; nothing edited. Hashes: `scripts/runtime/skills.lock.json`.
- Excluded on purpose: every other skill (review-animations etc. are human-slash-only), README, plugin manifests
- Status: **dormant**. Not under `skills/`, no registry record, no worker exposure, no hooks, no scripts. Activation needs a separate approval.
- Note: The human-slash-only skills (e.g. `review-animations`) are not staged.
- Verify: `uv run python scripts/verify_skills_lock.py`
- Rollback: `git rm -r third_party/emilkowalski-skill`, delete the `emilkowalski-skill` entry in `scripts/runtime/skills.lock.json` and its source in `config/skills.yaml`.
