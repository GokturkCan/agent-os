# Efficiency patterns (R3.5): reuse audit, measured changes, compatibility, deferrals

Branch `feature/run3-efficiency-patterns` (from the PR #3 tip; not pushed). Production stays: SystemOne `null`, `fastgate.model: null`,
`activation` allowlists empty. Nothing here is wired into Hermes, a hook, an MCP tool or a router stage; every module is opt-in and offline.
Token figures are `ceil(chars/4)` estimates, not tokenizer-measured. All new fixtures are **model-assisted, not human-reviewed**.

## 1. Reuse vs new

| Area | Existing (kept) | Changed | New |
|---|---|---|---|
| FastGate / SystemOne contract, adapter, compat | `systemone.py`, `systemone_adapter.py`, `systemone_compat.py` | compat adds an additive typed `trace` (reason, fallback, latency; no inputs/model text) | – |
| WakeGate | deterministic must-wake rules, skip limit, no-change defer | must-wake vocabulary widened (see §2) | – |
| ContextGate | content-addressed store, KEEP/TRUNCATE/DROP, protected lines, SecondBrain refusal | failure-signal and identifier protection (see §2) | – |
| ToolPruner | passthrough/structured/progress/collapse/chunk logic | shares the widened failure-signal layer (not the identifier layer) | – |
| Rule reuse (Unclutter pattern) | `rulecache.py` (human-approved, scoped, config-hash-invalidated, revocable) | none | – |
| Retrieval selection | – | – | `retrieval_select.py` (BM25 over a supplied pack, source attribution, optional re-rank, citation verifier) |
| Evaluation harness | `module_eval.py` + v1 suites | `--suite-file`, WakeGate `must_wake_rule_coverage`, `retrieval` suite | v2 dev/holdout fixtures, retrieval suite |

Historical evidence verified from `audit/systemone-eval-r3.2g/modules-recovery/*-final.json` (unchanged, not rewritten): ContextGate 35/35 essential facts kept
(0 false drops, exact recovery, 50.7% deterministic reduction); ToolPruner 27/27 kept (46.1%); deterministic WakeGate 0 missed important events (14 unnecessary
wakes); Laya-assisted WakeGate missed 1 (acceptance failed). Those suites were authored by the same session that built the modules, which is why §2 adds fresh fixtures.

## 2. Measured changes (baseline = unchanged code; `audit/efficiency/baseline/*.json` vs `audit/efficiency/after/*.json`)

Method: fixtures written and committed (`17c246a`, hashes in `audit/efficiency/fixtures-freeze.json`) **before** any measurement or code change; baseline measured; code tuned
using DEV only; holdout re-measured. **Caveat that limits the evidence:** the same model-assisted author wrote dev, holdout and the fix, and knew the holdout's failure
classes, so the holdout is *not* an uncontaminated generalisation test. Treat holdout numbers as "no regression and covers the classes I could think of", not as proof.

| Metric | Baseline dev / holdout | After dev / holdout | v1 suites (35/35, 27/27) |
|---|---|---|---|
| ContextGate essential facts lost | 7/7 and 9/9 (all) | **0/7, 0/9** | still 0/35, reduction 50.7% (unchanged) |
| ContextGate token reduction | 80.6% / 78.8% (by dropping the evidence) | 69.4% / 68.9% | 50.7% |
| ToolPruner essential lines lost | 0/12, **1/14** | **0/12, 0/14** | still 0/27, 46.1% |
| ToolPruner token reduction | 15.4% / 13.8% | 15.5% / 13.3% | 46.1% |
| WakeGate critical events caught by a *rule* (not by fallback) | 0/5, 1/9 | **5/5, 9/9** | – |
| WakeGate false negatives (rules-only) | 0 / 0 | 0 / 0 | 0 |
| WakeGate unnecessary wakes | 3 / 5 | 3 / 5 (unchanged) | – |
| Latency per transcript/output/event (p50, deterministic) | 1.4 ms / 0.1 ms / 0.01 ms | 2.6 ms / 0.1 ms / 0.01 ms | – |

What the numbers mean:
* ContextGate: the baseline's higher reduction was **false economy** (it discarded every essential fact lacking an "error"-style keyword: HTTP 429/503, ECONNREFUSED, CrashLoopBackOff,
  OOMKilled, segfault, commit/ticket/id/port/version pins). The fix costs ~10 points of reduction on the new fixtures and none on v1. Rejected-optimization rule applied: retention wins over tokens.
* ToolPruner: only one lost line on the holdout (CrashLoopBackOff). The first draft of the shared signal regex was case-insensitive and matched any word starting with "e" (`E[A-Z]{3,}`), cutting v1 ContextGate
  reduction to 31%; found by ablation and fixed (errno/signal names are now case-sensitive; v1 back to 50.7%). Identifier protection is ContextGate-only because it matches ordinary log noise.
* WakeGate: the real finding is **rule coverage**. In rules-only mode every undecided event wakes, so the earlier "0 missed" was true but fragile: with a model allowed to defer, 8 of 9 holdout critical events
  (expired/denied/rejected/refused/overdue/unreachable/killed, EN+TR) were not protected by any rule. They are now, and a test proves a model that always says "defer" cannot suppress any of them.
  I also tried a bulk-mail defer rule; it **never fired** (every bulk fixture contains a must-wake trigger word by design), its benefit was unmeasured, so it was removed. Unnecessary wakes are unchanged.
* New rules are deliberately broad substring/word-start matches: more false wakes/keeps are the accepted failure direction. Not covered: negations ("no errors"), non-EN/TR languages, free-form identifiers.

### Neural vs deterministic on identical holdout fixtures (local Laya-MLX only; Open-Jev not run — 6.4 GiB, no need after the above)
| | deterministic | + Laya | |
|---|---|---|---|
| ContextGate reduction / drops | 68.9% / 0 | 63.5% / 0, 8 calls, p50 28.6 ms, max 512 ms | model keeps *more*; no retention gain |
| ToolPruner reduction / lost | 13.3% / 0 | 7.6% / 0, 19 calls | model keeps more; no gain |
| WakeGate unnecessary wakes / FN | 5 / 0 | 5 / 0, 2 calls | no gain |
| Retrieval recall@1 / @3 / MRR (15 queries) | BM25 .733 / .867 / .789 | re-rank .800 / .867 / .833 | +1 query of 15, within noise |
Conclusion: no neural path earned its place (consistent with R3.2C: Laya shows no semantic skill). The deterministic implementations stay the default; model paths stay opt-in.

### Retrieval selection (new, tiny synthetic suite: 42 notes, 15 EN/TR queries, 10 citation cases; `evals/data/retrieval-suite-v1.yaml`)
naive word overlap recall@1 .667 / recall@3 .733; BM25 .733 / .867 (lexical queries .818 / 1.0; **vocabulary-mismatch queries .5 / .5**, the known limit). Embedding selection: **not measured —
no embedding model is installed and none was downloaded.** Citation verification: 0 false accepts, 0 verdict mismatches (unknown source, source outside the selected pack, quote the source does not contain,
paraphrase, empty quote and non-dict garbage are all rejected). One fixture expectation (c10) was corrected after the first run because it contradicted the documented check order (pack membership before quote); disclosed here.

### Resource, privacy, cost, failure behaviour
Pure-Python, single process, no network, no API call, no model load unless the caller passes a backend. ContextGate/pruner stores are content-addressed and refuse any path inside `~/SecondBrain`;
originals are never modified. Failure direction everywhere: keep/wake/escalate. A Laya backend, if used, adds ~1 GiB RSS and one process (measured earlier, R3.2G).

## 3. Architecture compatibility report
* Hermes remains the only orchestrator; nothing adds a router, gateway, daemon, MCP tool, hook or dependency. The modules are library functions + `agentos module-eval` CLI.
* Typed question/answer, explicit backend selection, raw-vs-calibrated confidence, abstention-as-escalation, closed error vocabulary and deterministic fallback already exist in `systemone.py`/`systemone_adapter.py`;
  R3.5 reuses them (modules call `S.system_one`). Observability gap closed minimally (compat `trace`).
* Patterns taken from the reviewed ecosystem (`audit/r3.2g-ecosystem-review-2026-10-14.md`, pins in `r3.2g-ecosystem-pins.json`): LiteLLM complexity-router "rules before classifier, fall back on failure" → WakeGate/ContextGate
  ordering; Vercel/Pydantic AI typed Choice + "tools proposed, not called" → already the SystemOne contract; fast-jev-compaction KEEP/TRUNCATE/DROP + exact text → ContextGate; jev-pruner → ToolPruner;
  Unclutter template rules → `rulecache` (unchanged, human approval required). No upstream code was fetched or executed in this task.
* Rule reuse: existing `rulecache` behaviour suite still passes (no hits before human approval; non-human approval refused; config change invalidates; rule never adds an option; revocation works). Model output alone can
  never create or approve a rule. No rule is approved; auto-proposal volume (64 on the dev set) is a review burden, not a feature.

## 4. Phase 4 — browser/CUA reference notes (research only, nothing implemented)
Design requirements distilled from the already-reviewed references (jev-ultrafast, mobile-jev, jevpilot, voice-browser, minecraft-agent), for any future scoped milestone:
1. Offer the model an **indexed, enumerated action table built by code** from the observable state (only supported operations on existing targets); the model picks an index, never a free-form action.
2. Bind every action to a **state fingerprint** (hash of the observed page/UI state + target id); if the state changed since observation, the action is stale → re-observe, do not execute.
3. Questions with one eligible answer are resolved in code; abstain/escalate is a first-class answer.
4. A separate, text-only helper may draft free text; it can never choose targets or operations.
5. Sensitive operations (payment, credential, permission, external publish, delete) require **named human approval** through the existing risk gate, never a model decision.
6. Default dry-run/observe-only; trace every step. Paid device/browser APIs (mobile-jev), autonomous spending (Automaton) and trading (jev-trader) stay rejected. Existing Playwright MCP is the only browser capability and is untouched.

## 5. Explicitly deferred
LiteLLM/Vercel/Pydantic AI/Ollaya/open-jev-bridge integration (no unmet requirement); embedding retrieval (needs an approved model); neural pruning/compaction/wake models (no demonstrated gain);
a deterministic bulk-mail defer rule (needs plain-bulk fixtures to prove value); wiring any module into Hermes/hooks (needs explicit approval); Open-Jev v3 independent evaluation (paused on branch
`feature/run3-openjev-optimization`, no commits); autonomous browser/mobile control; human review of all fixtures.
