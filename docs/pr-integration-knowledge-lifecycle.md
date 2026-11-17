# PR: Knowledge lifecycle + Hermes P0 integration

**Branch:** `integration/knowledge-lifecycle-e2e` (base: `origin/main`)

## Summary

- Land knowledge lifecycle, recall, continuity, Hermes skills, worker env hardening.
- Hermes `external_dirs` retargeted locally to `~/agent-stack-integration/skills` (user machine; not in repo).
- Deterministic Hermes contracts: `knowledge remember`, `knowledge where-stopped`.

## Test plan

- `pytest tests/test_knowledge_lifecycle.py tests/test_recall.py tests/test_project_workflow.py tests/e2e_acceptance.py tests/test_hermes_knowledge_contract.py`
- `pytest evals/test_hermes_integration.py`
- Live: Hermes `remember` + `where-stopped` smoke (post-skill update)

## Not included

- No canonical vault apply; historical `kp-eccc7d1772f54c80b1d5ce5e` unchanged.
- Run 3.6 audit artifacts remain out of tree.

## Merge notes

After merge, users run `scripts/hermes-wire.py retarget --i-approve` if skills path still points at legacy checkout.