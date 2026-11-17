# Knowledge Lifecycle Review Workflow

## Overview

Moving a DRAFT proposal through the knowledge lifecycle requires 6 authorized steps. No automatic approve/commit command exists — human review through the existing reviewer/claude-obsidian workflow is required.

## Steps

### 1. Reviewer Confirms Proposal Identity
- Confirm proposal/project identity, authorized summary, provenance, affected paths, unchanged guard writes, human intent and uncertainty
- Check artifact SHA-256 and every expected canonical hash
- Any conflict requires a new draft, not refreshed hashes on the old plan

### 2. Stage Capture in Vault Inbox
- Stage `capture.md` in the vault inbox
- Run `Vault.capture` to create `.raw/captured/<raw_sha256>.md`
- Verify bytes match reviewed payload

### 3. Create Engine Proposal
- Create `Vault.propose(id, "ingest", plan["writes"], proposer, source_manifest_updates=..., address_requests=...)`
- This invokes engine inspection and yields the expanded engine approval hash
- Do not hand-author or skip this hash

### 4. Obtain Human Approval
- Obtain actual human approval of the exact inspected plan
- Use `Vault.approve` with independent reviewer and genuine human reference
- The test helper's `human:test-only-explicit-approval` is never authorization for a real vault

### 5. Apply Through Vault
- Apply through `Vault.apply`
- Engine's CAS, confined paths, lint, journal and backups remain in charge

### 6. Reconcile
- Run `agentos knowledge reconcile <id>` to observe APPROVED or record COMMITTED
- Only after complete matching journal, exact resulting file hashes and successful lint
- Recall the project to verify visibility

## Key Constraints

- **No lifecycle `approve` or `commit` command** — worker success, LLM review, or guessed approval reference is never human approval
- External reviewer/claude-obsidian workflow must handle the actual approval
- Rejected proposals never reach the gate; rejection is refused if an engine transaction has already started/completed
- If lifecycle exits after engine commits but before receipt is saved, restart and `reconcile <id>`; it reconstructs the receipt from the approved journal and current hashes (idempotent)
- For incomplete engine journal, reconciliation reports `recovery_required`; authorized reviewer uses existing `claude-obsidian transaction recover --vault ...` mechanism

## Reference Proposal

- Current DRAFT: `kp-0c2564824e6ea99c393d443f` (Agent OS onboarding)
- State: DRAFT, created 2026-11-13T03:19:07+00:00
- Target: wiki/projects/prj-9c588b6b1fd1ce3f1b1d.md

## Related Skills

- `knowledge-lifecycle` — full lifecycle commands and contracts
- `secondbrain-recall` — required before answering questions about saved knowledge