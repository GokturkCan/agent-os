# PR: Knowledge lifecycle + Hermes P0 integration

**Branch:** `integration/knowledge-lifecycle-e2e` (base: `origin/main`)

## Summary

- Land knowledge lifecycle, recall, continuity, Hermes skills, worker env hardening.
- Hermes `external_dirs` retargeted locally to `~/agent-stack-integration/skills` (user machine; not in repo).
- Deterministic Hermes contracts: `knowledge remember`, `knowledge where-stopped`.
- NL workflow: `workflow request` + skill `agent-os-workflow`; graph + learning closure fixture E2E.
- Live integration test: authorized `claude_code`/`codex` dispatch fail → repair → verify (`tests/test_authorized_worker_repair.py`).

## Test plan

- `pytest tests/test_knowledge_lifecycle.py tests/test_recall.py tests/test_project_workflow.py tests/e2e_acceptance.py tests/test_hermes_knowledge_contract.py tests/test_workflow_graph.py tests/test_hermes_workflow_integration.py tests/test_learning_closure.py`
- `pytest tests/test_authorized_worker_repair.py` (live worker; requires `codex` or `claude` on PATH)
- `pytest evals/test_hermes_integration.py`
- Live: Hermes `workflow request` + `remember` + `where-stopped` smoke (post-skill update)

## Not included

- No canonical vault apply; historical `kp-eccc7d1772f54c80b1d5ce5e` unchanged.
- Run 3.6 audit artifacts remain out of tree.

## Merge notes

After merge, users run `scripts/hermes-wire.py retarget --i-approve` if skills path still points at legacy checkout.