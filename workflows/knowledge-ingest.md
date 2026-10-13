# Workflow: SecondBrain ingest / durable lesson

Verified by `evals/test_a1_knowledge.py` and `evals/test_a8_durable_lesson.py`
against throwaway vaults created by the claude-obsidian engine.

```
worker result
  -> Hermes: durable? (config/knowledge.yaml memory_admission)
  -> stage file in ~/SecondBrain/inbox/        (workers may write here only)
  -> Vault.capture([...])                       .raw/captured/<sha256>.<ext>, create-only
  -> ingest_source_writes() / lesson_writes()   page + source/claim ledger + log/index
  -> Vault.propose(op_id, ..., proposer)        bundle pinned to expected hashes;
                                                engine `inspect` -> approval_sha256
  -> human reviews bundle (state/knowledge/proposals/<op>.json)
  -> Vault.approve(op_id, reviewer != proposer, approval_sha256, human_approval_ref)
  -> Vault.apply(op_id)                         engine CAS; refuses if anything changed
  -> lint (0 issues expected)
```

Provenance chain preserved: wiki page (`source_id`, `sha256`) -> source ledger
(`origin.locator` = raw path, `content_sha256`) -> `.raw/captured/<sha>` ->
`.raw/.manifest.json`. Lessons additionally carry `learned_from: <run_id>`.

Recovery: the engine journals every transaction with backups in
`.vault-meta/transactions/<op>/`; `claude-obsidian transaction recover` rolls
back interrupted operations. See `docs/rollback-recovery.md`.
