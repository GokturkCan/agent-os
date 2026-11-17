# Project knowledge lifecycle

This is a small extension of the existing Python Agent OS and claude-obsidian gate. There is no separate registry, database, index, memory framework, conversational agent, scheduler or daemon.

## Contracts and boundaries

| Stage | Responsibility and contract | Failure behavior |
|---|---|---|
| Capture | Explicitly authorized bounded summary, kind, project, evidence, actor/session and uncertainty → deterministic proposal ID | Reject absent authorization/provenance, detected secrets/personal data, raw transcript shapes or oversized input; no persisted capture |
| Classify | Exact normalized project ID/name/alias/repository/path from canonical notes | Missing/ambiguous stays unresolved; no fuzzy single-keyword assignment |
| Retrieve | Existing BM25/claude-obsidian recall over a temporary copy of same-project pages | `ok`, `no_results`, `unavailable`; no real-vault index write |
| Context | Budgeted objective/project/decisions/facts/questions/citations/constraints/effective tool grants/output/acceptance | Exclude unrelated/sensitive pages; reject oversized header or disabled worker; unsupported claims never become verified facts |
| Execute | Existing dispatcher preflight selects the worker, then receives scoped context through its existing prompt argument | Existing capabilities, strict MCP selection, risk gates, task state, deadlines, retries and exclusive leases remain authoritative |
| Extract | Actual structured result + explicitly authorized summary + artifact hashes | Failed/partial results create no automatic proposal; worker reports retain uncertainty |
| Propose | DRAFT → READY_FOR_REVIEW; immutable plan digest, expected hashes, evidence payload, minimal writes and diff | Detect stale notes/evidence, unsafe paths, broken/cross-project links or tampered plan |
| Review | Existing gate's independent reviewer + explicit human reference, exact engine approval hash | No lifecycle approval API; no self-review or worker-success approval |
| Commit | **Authorized external reviewer/claude-obsidian mechanism only** | Expected-hash CAS refuses stale state; engine journals/backups recover failures |
| Verify | Read externally approved complete journal, compare approved input bundle and expanded output hashes, run lint, persist receipt | Refuse inconsistent journal/content or lint failure; surface engine recovery requirement |
| Recall | Same project-aware existing BM25 path sees committed canonical note with provenance | Source absence is explicit; content is untrusted reference data |

Operational records live under `${AGENTOS_STATE_DIR:-~/agent-stack/state}/knowledge/lifecycle/`. They are drafts, context packages, result metadata, review handoffs and receipts; they are not another canonical knowledge store. There is no automatic transcript capture.

`agentos knowledge --help` lists commands. JSON input is bounded to 64 KB. File-backed records use process locks, descriptor-relative no-symlink traversal, atomic replacement, fsync and deterministic IDs. Capture deduplication includes project, content, evidence, operation and originating actor/task. Committed records are immutable audit receipts; their hashes describe the verified transaction moment, not a promise that future authorized edits cannot occur.

## Project identity and canonical layout

Project identity is derived read-only from `wiki/projects/*.md`, legacy `type: project` notes or `entity_kind: project` notes. Prefer an explicit stable `project_id`. Legacy notes without an ID derive one from `source_id` or stable note path and should receive an explicit ID through a reviewed update before renaming.

The installed engine's vocabulary uses `type: entity`, so new project proposals use `entity_kind: project` rather than inventing an incompatible engine page type. Optional frontmatter: `canonical_name`, `aliases`, `scope`, `status`, `repositories`, `paths`, `references`, `research_questions`, `decisions`, `experiments`, `open_questions`. Metadata and source references are retained. Duplicate identities or shared aliases resolve as ambiguous rather than choosing a winner.

Other knowledge is filed under the existing `wiki/concepts`, `wiki/research`, `wiki/decisions` and `wiki/sources` conventions with `project_id`, `record_kind`, `evidence_status` and the existing source/claim ledger provenance. Updates append a clearly marked change/evidence section, preserving the previous file bytes, frontmatter and links. Supersede/contradict proposals preserve the old claim and record the proposed change rather than silently deleting history.

A ready plan includes unchanged guard writes for project/source dependencies. The installed engine rejects expected hashes for paths outside its write-set, so the guard writes carry byte-identical content through its existing supported CAS boundary. They do not change note contents, are visible in `handoff.json`, and a concurrent project-scope edit causes the engine to refuse apply. No engine patch or policy change is needed.

## Authorized reviewer handoff

Real SecondBrain policy gives the control-plane operator no direct canonical write authority. The lifecycle therefore has **no approve/apply/commit command**. Its `export` only creates artifacts outside the vault. This task does not approve any real canonical mutation.

The existing authorized independent reviewer must:

1. Open `review.md` and `handoff.json`. Confirm proposal/project identity, authorized summary, provenance, affected paths, unchanged guard writes, human intent and uncertainty. Check artifact SHA-256 and every expected canonical hash. Any conflict requires a new draft, not refreshed hashes on the old plan.
2. Through the existing allowed capture mechanism, stage `capture.md` in the vault inbox and run `Vault.capture` to create exactly `.raw/captured/<raw_sha256>.md`. Verify its bytes match the reviewed payload. No raw conversation or secret is included.
3. Create the existing `Vault.propose(id, "ingest", plan["writes"], proposer, source_manifest_updates=..., address_requests=...)`. This invokes engine inspection and yields the expanded engine approval hash, including address allocation and manifest changes. Do not hand-author or skip this hash.
4. Obtain actual human approval of that exact inspected plan, then use the existing `Vault.approve` with an independent reviewer and genuine human reference. The test helper's `human:test-only-explicit-approval` is **never** authorization for a real vault.
5. Apply through the existing `Vault.apply`. The engine's CAS, confined paths, lint, journal and backups remain in charge. No lifecycle helper grants new permissions or writes canonical files itself.
6. Run `agentos knowledge reconcile <id>` to observe APPROVED or record COMMITTED only after a complete matching journal, exact resulting file hashes and successful lint. Recall the project to verify visibility.

The human approval/engine operation is deliberately not automated by this interface. An authorized reviewer can use the existing low-level workflow; it is not made available to workers by this change. Existing approval records remain the authoritative authorization source. Merely supplying an approval-looking string to a new command cannot commit knowledge.

## Recovery

If the lifecycle exits after the external engine commits but before the receipt is saved, restart and `reconcile <id>`; it reconstructs the receipt from the approved journal and current hashes. It is idempotent.

For an incomplete engine journal, reconciliation reports `recovery_required`. The authorized reviewer uses the existing `claude-obsidian transaction recover --vault ...` mechanism. The lifecycle never performs its own canonical rollback. The upstream engine's deterministic failure injection is tested in a disposable vault, proving rollback and a subsequent successful retry. A rejected proposal never reaches the gate; rejection is refused if an engine transaction has already started/completed.

## Worker contract

The scoped dispatcher defaults to dry-run. `--execute` is an explicit request to invoke **existing** execution semantics, including local task-branch commits; this implementation task did not launch a paid model worker or commit to the real repository.

Input: task ID, registered repository, project identity, objective, original-source citations/hashes, relevant decisions/facts/questions, constraints, acceptance and expected structured result. Existing launch policy controls actual tools; retrieved prose cannot grant capabilities. A context mismatch on retry requires a new task ID or explicit replan rather than silently changing the durable task contract.

Output: actual Agent OS task ID, worker, status/exit state, deterministic verification and artifact paths/hashes, plus an authorized bounded summary. Attested success must match the recorded dispatch outcome and closed task state. An unmatched external report is explicitly unverified, needs scoped artifact evidence even for a draft, and never becomes an attested worker success. Contexts/results belonging to another registered project are refused.

OpenCode, Cursor and Antigravity may later implement this same input/output contract as isolated workers, after approved enforcing adapters for capability policy, credential isolation, worktrees, leases, cancellation and verification. They are not enabled here. Workers remain broad-purpose; projects do not receive permanent agent domains.

## Hermes and Obsidian

The repository skill `knowledge-lifecycle` is loaded through the existing Hermes external-skill directory. No global provider/model/memory configuration is changed. Hermes still decides what to capture and dispatch, and presents human review; no new conversational manager is introduced.

`knowledge navigation` writes `navigation.md` in operational state, with Projects, Ideas, Decisions, Research questions, Experiments, Pending proposals and source links. Each exported proposal has a human-readable diff. These are Markdown previews outside the vault, not a vault redesign or plugin installation. Do not copy previews into canonical wiki without review.

The real vault currently may have no project notes. `knowledge projects` reports the actual catalog; a missing project must first be proposed and approved, never silently invented.

## Verification scope

`tests/test_knowledge_lifecycle.py` exercises real file-backed lifecycle behavior and the installed transaction/retrieval engine against disposable vaults. Worker execution tests use a synthetic runner through the real dispatcher/worktree/lease machinery; no model inference is claimed. Existing full regressions and protected-manifest checks run separately. Hermes discovery/lint/guard tests use the installed Hermes code with a temporary Hermes home; they do not prove an actual natural-language Hermes conversation selected and executed the skill.
