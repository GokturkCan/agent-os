# R3.2C Phase 1 — semantic decision-quality evaluation of SystemOne backends (2026-10-14)

**Scope:** a reproducible evaluation framework for SystemOne worker-choice decisions, and the first
quality measurement of the existing Laya-MLX candidate. No new model was installed. The production
SystemOne backend stays `"null"`, `fastgate.model` stays `null`, nothing is promoted, and all confidence
values stay `kind="raw"` (never thresholded).

## Verdict

| Question | Answer |
|---|---|
| Does R3.2C **Phase 1** pass acceptance? | **Yes** — framework, grounded dataset, three-layer harness, formulation change, safety tests and reproducible evidence are delivered (criteria below). |
| Did Laya show **semantic decision skill** on this set? | **No, not demonstrated.** Its choices follow the *label string*: swapping two workers' descriptions leaves 94.6% of choices unchanged (70/74). Its best variant scores 0.649 vs 0.714 for a constant "always claude_code" rule and 0.552 for random. |
| Is the new formulation better? | **Mixed and narrow.** It lowers forbidden picks (0.234 → 0.149) but only by avoiding the one blatantly different worker; on the production-relevant claude_code/codex pair it changed 48/72 → 49/72. It also made order-consistency worse (0.860 → 0.640). |
| Recommendation | **Keep Laya as a *baseline* for Phase 2; do not promote it, and do not invest in further Laya-specific prompting.** See the end. |

## Acceptance criteria for Phase 1

| Criterion | Result |
|---|---|
| Question formulation carries authoritative option descriptions, never widening eligibility | PASS — `systemone_options.py` + adapter validation; tests in `evals/test_systemone_options.py` |
| Deterministic, reviewable labeled dataset with rationale/constraints; policy vs semantic separated | PASS — 66 cases (61 semantic, 5 policy; 10 escalation-gold), 12 end-to-end cases, 17 cited facts |
| Labels grounded in the real registry/config, not invented | PASS — executable grounding tests (they caught one wrong label, see Dataset) |
| Separate harness reporting decision quality / protocol compliance / end-to-end routing as different metrics | PASS — `agentos/systemone_eval.py`; `systemone_bench.py` untouched |
| High-risk / forbidden picks cannot count as success | PASS — scored `unsafe_selection` / `forbidden_choice`; mutation-checked |
| Laya evaluated, successes **and** failures recorded; label-preference claim tested | PASS — every decision is in `laya-mlx.json`; counterfactual swap probe |
| Reproducible (seeds, hashes) and old R3.2B results unchanged | PASS — decision hashes identical across independent runs; R3.2B benchmark hash identical |
| Defaults, approval gate, fallback and permissions unchanged | PASS — see regression tests |

## What changed (exact)

- `agentos/systemone.py`: `SystemOneRequest` gains optional `option_info` and `allow_abstain` (defaults keep every existing caller and backend working); reason code `backend-abstained`.
- `agentos/systemone_options.py` (new): builds compact option metadata **only from existing config**: `roles` and `interactive` (workers.yaml), `access`/`latency` (providers.yaml), `cost`/`locality` and the per-request `missing` capability list (capability registry, via the capability plane's own integration logic). Free-text notes are excluded; a worker not in the registry gets no `missing` field (nothing is invented).
- `agentos/systemone_adapter.py`: `sanitize_option_info()` — allowlisted fields and types, ids outside the offered options are dropped (metadata can never introduce an option), unknown fields rejected, lists over 8 items rejected rather than truncated, secret-looking text rejected, total payload still capped at 4096 B. Abstention is parsed as an **escalation** (`backend-abstained`), only when the request allowed it. Wire format stays protocol v1 and is additive: a request with neither field is byte-identical to R3.2B.
- `agentos/router.py`: attaches the metadata and an improved question prompt to the request (advisory; failure to build it never fails routing). Abstention is **not** enabled in production.
- `agentos/systemone_workers/laya_worker.py`: renders the structured metadata into deterministic description text (never model-generated) and offers an optional "none fits" label. The legacy path is unchanged (R3.2B benchmark hash re-verified identical).
- `agentos/systemone_eval.py` + `agentos systemone-eval` (new), `evals/data/systemone-decisions-v1.yaml` (new, protected judge), tests `evals/test_systemone_options.py` and `evals/test_systemone_eval.py`.
- Note: the brief names `agentos/systemone_laya.py`; no such file exists. The Laya-specific code is `agentos/systemone_workers/laya_worker.py`.

## Dataset construction and limits

Hand-authored from repository config; every case cites facts (`facts:`) and a rationale. Gold strength is explicit: **strict** (hard facts: capability support, interactive=false, risk gate, sole option; 33 cases), **rule** (explicit config rules: reviewer independence, escalation target, subscription vs API; 7) and **intent** (documented `roles`; 26 — *configured intent, not measured performance*).

- **Revision on record:** `cap-005` was first labeled "claude_code only" but the registry also provides `devops.github` through `gh-cli` (needs only `devops.shell`, native to both), so codex is not missing it. An automated grounding test found this *after* an exploratory run; the label was corrected from the registry's facts (not any model output) and recorded in the dataset's `revision_log`; it is now a control case. All committed evidence comes from the corrected set. The correction moved the bare variant by under one point.
- **Imbalance:** `claude_code` is acceptable in ~71% of answerable cases (the registry gives it more integrations), so "always claude_code" scores 0.714. The report therefore always shows baselines and a **counter-prior** metric (cases where claude_code is *not* acceptable).
- **Capability-difference cases are defense-in-depth probes:** in production the capability plane removes a worker lacking a capability *before* SystemOne runs.
- `state.need` (the task's primary need) is an **evaluation-assumed upstream signal**; the production router does not produce it yet.
- 66 cases hand-written by the config's authors: no statistical generalization, and decisions are correlated (cases × option orders).

## Methodology

Each case is evaluated under **every ordering** of its options (the dataset order first; 180 decisions per variant), for three formulations: **bare** (ids only, R3.2B), **described** (authoritative metadata + task-oriented prompt), **described+abstain** (adds an explicit "none fits" option, mapped to an escalation).

Three metrics families that are **not interchangeable**:
1. **Layer 1 — backend decision quality** vs labeled gold. A pick on an escalate-gold case is an `unsafe_selection`; a pick in `forbidden` is a `forbidden_choice`; an escalation is safe but never a success.
2. **Layer 2 — adapter/protocol compliance:** every response well-formed, offered option only, closed reason vocabulary, raw confidence, no exception. Says nothing about quality.
3. **Layer 3 — end-to-end policy-valid routing:** the real router with the backend selected (risk gate, eligibility, health, fallback), 12 cases. Measures policy validity of the final route, not optimality; it uses only what the router produces today, so it does not see `need`.

Also: a separate **policy suite** (single/empty options, metadata cannot widen) that tests the contract rather than the model; reference baselines; a **counterfactual description-swap probe**; abstention diagnostics. Seed 1337; per-variant decision-sequence hashes.

## Results — Laya (answerable decisions n = 154; escalation-gold n = 20)

### Layer 1 — decision quality (acceptable = chose a gold-acceptable worker; escalations count as not acceptable)

| System | Acceptable-choice rate | Answered precision | Escalated | Forbidden picks | Counter-prior acceptable |
|---|---:|---:|---:|---:|---:|
| Laya **bare** (R3.2B formulation) | 0.539 | 0.539 | 0.000 | 0.234 | 0.289 |
| Laya **described** | 0.649 | 0.649 | 0.000 | 0.149 | 0.467 |
| Laya **described + abstain** | 0.305 | 0.839 | 0.636 | 0.039 | 0.378 |
| baseline `first` | 0.558 | 0.558 | 0.000 | 0.201 | 0.422 |
| baseline `last` | 0.558 | 0.558 | 0.000 | 0.201 | 0.422 |
| baseline `label-prior` | 0.714 | 0.714 | 0.000 | 0.000 | 0.022 |
| baseline `random` | 0.552 | 0.552 | 0.000 | 0.195 | 0.422 |

### Layer 1 — escalation and policy

| System | Escalation-gold: correct | Unsafe selections | Policy compliance | Violations (count) |
|---|---:|---:|---:|---:|
| Laya **bare** (R3.2B formulation) | 0.000 | 1.000 | 0.391 | 56 |
| Laya **described** | 0.000 | 1.000 | 0.533 | 43 |
| Laya **described + abstain** | 0.750 | 0.250 | 0.880 | 11 |
| baseline `first` | 0.000 | 1.000 | 0.446 | 51 |
| baseline `last` | 0.000 | 1.000 | 0.446 | 51 |
| baseline `label-prior` | 0.000 | 1.000 | 0.783 | 20 |
| baseline `random` | 0.000 | 1.000 | 0.457 | 50 |

Baselines never abstain, so they can never pass an escalate-gold case; that is a property of the baseline, not evidence about a model.

### Layer 1 — robustness and sensitivity

| System | Same choice in every order | Correct in every order | First-listed share | Discriminate groups passed | Invariant groups passed | claude_code share (2-worker) | claude_code share when gold = codex |
|---|---:|---:|---:|---:|---:|---:|---:|
| Laya **bare** (R3.2B formulation) | 0.860 | 0.580 | 0.441 | 0.000 | 1.000 | 0.931 | 1.000 |
| Laya **described** | 0.640 | 0.540 | 0.395 | 0.100 | 1.000 | 0.847 | 0.800 |
| Laya **described + abstain** | 0.020 | 0.060 | 0.182 | 0.100 | 0.250 | 0.500 | 0.222 |
| baseline `first` | 0.000 | 0.180 | 1.000 | 0.000 | 1.000 | 0.500 | 0.500 |
| baseline `last` | 0.000 | 0.180 | 0.000 | 0.000 | 1.000 | 0.500 | 0.500 |
| baseline `label-prior` | 1.000 | 0.720 | 0.414 | 0.000 | 1.000 | 1.000 | 1.000 |
| baseline `random` | 0.340 | 0.340 | 0.342 | 0.300 | 0.250 | 0.486 | 0.450 |

An "invariant" pass is only meaningful together with a "discriminate" pass: a constant function is perfectly invariant (see `label-prior`).

### Layers 2, policy suite and latency

| System | Layer 2 protocol compliance | Policy suite passed | Policy suite safe degradations | Latency p50 ms | Latency p95 ms |
|---|---:|---:|---:|---:|---:|
| Laya **bare** (R3.2B formulation) | 1.000 | 5/5 | 0 | 18.92 | 21.654 |
| Laya **described** | 1.000 | 5/5 | 0 | 26.526 | 29.433 |
| Laya **described + abstain** | 1.000 | 2/5 | 4 | 27.779 | 33.676 |
| baseline `first` | 1.000 | 5/5 | 0 | 0.001 | 0.002 |
| baseline `last` | 1.000 | 5/5 | 0 | 0.001 | 0.001 |
| baseline `label-prior` | 1.000 | 5/5 | 0 | 0.001 | 0.002 |
| baseline `random` | 1.000 | 5/5 | 0 | 0.001 | 0.002 |

### Layer 3 — end-to-end policy-valid routing

Laya (and every baseline): **12/12 policy-valid** (1.000). The high-risk gate stops routing before the backend is consulted, unhealthy and capability-excluded workers are never chosen, and a failing backend degrades to deterministic routing. A perfect Layer 3 does **not** imply good Layer 1 decisions: routing stays safe *because the policy layer is authoritative*, not because the model is right.

## Findings and counterexamples

1. **Label, not description, drives Laya's choice.** Counterfactual swap of the claude_code/codex descriptions (labels kept): choice unchanged in 70/74 decisions (94.6%); it flipped with the description in only 4. A description-following backend would flip ~100% (verified with a synthetic backend in the tests).
2. **The prior gain is real but narrow.** Paired bare → described: 24 decisions improved, 7 worsened, 123 unchanged (indicative only; decisions are not independent). On `{claude_code, codex}` alone: 48/72 → 49/72. In three-option sets: 33/80 → 49/80, caused by choosing `deepseek_harness` when it is not acceptable 45/62 → 23/62 times — it reacts to the one blatantly different description (`background only, not interactive; access: api`), not to claude-vs-codex facts.
3. **The R3.2B label preference persists.** When codex is the only acceptable answer, Laya chose it 0/20 times (bare) and 4/20 (described); claude_code was chosen in 0.847 of two-worker decisions. (R3.2B: 109/109 on an unlabeled workload.)
4. **Reviewer independence is inverted (0/8 in both formulations).** Given `primary_worker: claude_code` and the rule "prefer a different harness", Laya picks claude_code; given `codex`, codex. It copies the worker named in the state. Counterexamples: `rev-001`…`rev-004`.
5. **`discriminate` groups pass 0.100.** Changing the task's need (tests vs architecture, implementation vs hard debugging) does not change its choice appropriately; resource-state distractors do not change it either (invariant 1.0, but trivially).
6. **Abstention is not informative.** It fired on 0.638 of answerable and 0.750 of escalate-gold decisions (precision of abstention 0.133), did not pass 3 of the 5 contract cases because it abstained (on two single-option requests and on both orders of the metadata-widening case): safe, but not a pass, and wrecked order-consistency (0.020). When it *did* answer, precision was 0.836 (vs 0.691 for the plain variant on those decisions): a weak selective-prediction signal at ~36% coverage.
7. **Confidence is uninformative here.** Raw `answer_confidence` medians: correct 0.741 vs wrong 0.579 (described). Descriptive only; never used as a threshold.
8. **No protocol failures:** Layer 2 compliance 1.000 in every variant; no ineligible choice, exception or non-raw confidence.

## Operational impact (measured)

- Payload: mean 356 B (bare) → 913 B (described) → 934 B (+abstain); max 1,086 B of the 4,096 B cap.
- Warm decision latency (adapter, end to end): p50 18.92 → 26.526 → 27.779 ms (+40% described, +47% with abstain); p95 21.654 → 29.433 → 33.676 ms.
- Worker RSS ≈ 0.75–1.1 GiB (unchanged class). R3.2B committed benchmark hash re-verified identical after the worker change: `8cfe3aff326c8162…`.

## Reproduce

```bash
uv run agentos systemone-eval --backend laya-mlx --out audit/systemone-eval-r3.2c/laya-mlx.json
uv run agentos systemone-eval --backend baseline:label-prior      # also: first | last | random
uv run pytest -q evals/test_systemone_eval.py evals/test_systemone_options.py
```
Dataset SHA-256 `30e211a6ea922d6ad0ae7f1a5a65a5719a8c213efb8168f48fc991d4e7412396`; environment: Apple M4, 16.0 GiB, macOS 27.0.1; runtime laya-mlx 0.4.0, mlx 0.32.3, Python 3.11.13. Evidence was produced from the agentos tree at `6031a15` plus the uncommitted R3.2C changes (tree dirty = True), because this report ships in the same commit. Two independent runs gave identical per-variant decision hashes, probes and Layer 3 results (`reproducibility.json`).

## Regression and safety tests

New tests pin: metadata cannot widen eligibility or introduce an option; unknown/oversized/secret-looking metadata and malformed or missing replies fail closed; abstention is an escalation; the high-risk approval gate precedes the backend; adapter failure falls back to deterministic routing with metadata present; the null default and raw-only confidence are unchanged; gold labels agree with the registry/config; scoring cannot reward an unsafe pick; the committed evidence matches the dataset hash, recomputes from its own per-decision records, and contains no secrets or local paths. Mutation checks (four deliberate breakages: an escalate-gold pick scored as success, forbidden picks scored as merely wrong, metadata for un-offered ids forwarded, abstention enabled by default in the router) were each caught by the intended test.

**Final suite: 658 passed, 2 skipped** (the two skips are the pre-existing `AGENTOS_LIVE` tests; the live Laya tests ran); health 0 FAIL / 3 pre-existing WARN; manifest and `agentos validate` pass.

**Routing unchanged vs the release.** The released `v1.0.0` router and the current router produced identical `Decision` results (ignoring only the added `systemone` summary and trace lines) for **1000/1000** event/health combinations, including all 100 `classification` cases that exercise the SystemOne step (`v1-routing-differential.json`, with its matrix script). **Legacy benchmark unchanged:** the R3.2B decision-sequence hash (`8cfe3aff326c8162…`) is identical when re-run with the final worker.

**Evidence re-verified at finalization.** After an interrupted session the whole evaluation was re-run into a scratch location: all three variants' decision hashes, both probes, the 12/12 Layer 3 result and every per-decision outcome matched the committed `laya-mlx.json`, and the committed evidence files were byte-identical before and after. Every hand-typed figure in this report was re-derived from the evidence files.

## What this does and does not show

- Shows: the framework works, is reproducible, and can distinguish label-following from description-following; Laya, as formulated here, follows labels.
- Does **not** show: that Laya can never do this (a different formulation, calibration, or fine-tuning is untested), anything about production accuracy, or that any other backend is better. Nothing here is a statistical estimate.
- Deterministic policy already enforces every `strict` fact; SystemOne's residual job is `intent`-level preference, where Laya (described) scored 0.625 against 0.656 for random. Whether any model adds value over a deterministic tiebreak on weakly-grounded intent labels is itself unproven.

## Recommendation

**Keep Laya as a comparison *baseline* in R3.2C Phase 2; do not promote it and do not tune it further.** It is operationally excellent (fast, small, deterministic, fails closed) but, on this evidence, it is not making task-dependent decisions. Phase 2 (not started) should: compare other candidates on the same dataset and probes; add human-labeled cases; consider whether the residual intent-level decision needs a model at all; and treat "does it flip when the description flips" as a required gate. R3.3 calibration is premature until some backend shows semantic skill.
