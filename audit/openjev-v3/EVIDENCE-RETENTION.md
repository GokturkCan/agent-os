# Open-Jev v3 per-decision evidence: retention and verification

The R3.2H study produced ~17.7 MB of per-decision JSON (`dev/ cal/ opt/ final/`, 42 files). To avoid bloating the integrated Git history
with generated data, it is retained as **one deterministic 0.7 MB archive** plus a checksum manifest:

| Item | Path | Pin |
|---|---|---|
| Archive | `audit/openjev-v3/openjev-v3-evidence.tar.gz` | sha256 `080f96b3be23e7006497874e6c321b8008b8a8d550cbf77aadef98238daf7b2b` (684,715 bytes) |
| Manifest | `audit/openjev-v3/evidence-manifest.json` | sha256 + size + Git blob id of all 42 members; source commit `6765a27d84e554c09323b764184c10471758cf38` |
| Original blobs | branch `feature/run3-openjev-optimization` (PR #6), commit above | left untouched; nothing was deleted anywhere |

Small decision-relevant summaries stay in Git as plain files: `freeze.json`, `final-prerun.json`, `selection.json`, `report.json`,
`bench.json`, `bench-lazy.json`, `order-sensitivity.json`, and `../openjev-v3-closure-2026-10-18.md`.

## Verify (fails non-zero on any mismatch, missing or extra member)
```
uv run python scripts/openjev/evidence.py verify --archive audit/openjev-v3/openjev-v3-evidence.tar.gz
uv run python scripts/openjev/evidence.py verify --dir audit/openjev-v3        # after extraction
uv run python scripts/openjev/evidence.py verify --git                         # blobs at the manifest's source commit
```
## Restore and reproduce the report
```
uv run python scripts/openjev/evidence.py extract --archive audit/openjev-v3/openjev-v3-evidence.tar.gz   # verified; dirs are git-ignored
uv run python scripts/openjev/report.py      # byte-identical to the committed report.json (checked during integration)
```
`report.py` and `analyse.py` now refuse (IntegrityError) a result whose dataset sha256 differs from `freeze.json`, whose variants do not cover the
same cases, or whose outcome label is unknown (previously scored 0 silently), and refuse to run if any final system result is missing.

## Notes on pinned code
`freeze.json` records the sha256 of `agentos/openjev_opt.py` as it was at the freeze. During integration that research-only module (and
`openjev_scorer.py`) moved to `scripts/openjev/` so that no model-launching research code ships in the production `agentos` package; only import
lines, the docstring and the scorer-path lookup changed. The frozen original is `git show 6765a27:agentos/openjev_opt.py`.
The frozen datasets `evals/data/openjev-v3-{cal,opt,final}.yaml` are byte-identical to the frozen versions (checked by `evals/test_openjev_opt.py`).
