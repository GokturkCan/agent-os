# Open-Jev-2B v3 optimisation and independent evaluation (R3.2H) — closure (2026-10-18)

Branch `feature/run3-openjev-optimization` (from `2f9b498`). **Recommendation: Open-Jev as shipped = NO-GO. The optimised hybrid (neutral aliases + deterministic prefilter) = SHADOW-ONLY candidate,
not approved to start, and its advantage over the deterministic prefilter alone is NOT statistically established. Production stays NullBackend / `fastgate.model: null` / empty allowlists.**
Nothing was activated, registered, pushed or merged. R3.2C/F/G artifacts are untouched. No model was downloaded; no framework was installed.

## 1. What was built (research code only; not registered in `systemone.BACKENDS`, `config/systemone.yaml` or routing)
* `agentos/systemone_workers/openjev_scorer.py` — research scorer in the existing runtime venv: same checkpoint/loader/dtype as the shipped worker but returns the **full per-candidate probability vector** (the shipped worker discards it); reports `load_s`/`warmup_s`; optional `--idle-exit-seconds`.
* `agentos/openjev_opt.py` — cached score client (payload-hash cache; memory guard: stops if the median scoring time exceeds 4 s or system free memory < 15 %), deterministic **prefilter**, and `OpenJevBackend` with modes `baseline | canonical | alias | ensemble | deterministic`.
* `scripts/openjev/{author_v3,run_study,analyse,report,bench,lazy,order_sensitivity}.py`, `evals/test_openjev_opt.py` (17 tests, no inference), `evals/data/openjev-v3-{cal,opt,final}.yaml`.

## 2. Audit of the shipped scoring pipeline (verified in `state/runtime/openjev2b/src/jev`, no change made to it)
1. Each candidate is `name: description`, scored **independently** (no letters, no list position) → logits → softmax with the saved temperature (1.5188) → `argmax` (ties → first candidate). It is therefore inherently option-order invariant; the label *name* is visible to the model (the source of label reliance).
2. `format_response` returns the full probability dict, but the shipped worker keeps only `choice_confidence = (max − 1/n)/(1 − 1/n)` — an "excess over uniform" score, **not a probability**.
3. Abstention is just one more candidate (`none_fits`) competing in the softmax; it is exposed only in the `described+abstain` variant.
4. Reproducibility: my scorer in `baseline` mode vs the historical R3.2F run on the dev set: **540/540 records identical, max confidence difference 2.2e-16** (`audit/openjev-v3/dev/base.json` vs `audit/systemone-eval-r3.2f/openjev-2b.json`).
5. Permutation invariance, measured: for every request set in cal+opt (744 sets, all orders, 3 variants) the **maximum probability difference across orders is 0.0** and no argmax flips (`order-sensitivity.json`). The `canonical` (sorted) mode produced decisions identical to baseline — a guarantee, not an improvement.

## 3. Method and leakage controls
* **v3: 107 new scenario families** (EN+TR text, real and misleading labels ⇒ 4 observations/family, 428 cases) written before any v3 inference: coding intent (12 architecture/debug, 12 implementation/test), review independence, worker failure/unavailable, dynamic capability, interactive vs background, locality/cost, risk/approval, no-capable-worker escalation, insufficient/conflicting/equally-acceptable, single option, 6 prompt-injection/adversarial, 4 description-bias, plus counter-prior cases (gold excludes the label-prior first choice).
* Partitions, stratified per category, a family never crosses: **cal 33 families / opt 31 / final 43**. cal fits calibration; opt chooses the policy; **final was frozen (`audit/openjev-v3/freeze.json`, then `final-prerun.json` with the selection) before any final inference and run exactly once.**
* Selection rule (declared in `analyse.py::select`, applied to cal+opt only): max pooled utility, ties → fewer model calls. Result: **alias + prefilter**, with `tau = None` (the calibration-fitted confidence threshold did not improve opt utility, so no confidence-based abstention was adopted).
* Utility per decision (declared before final): correct +1, wrong-allowed −1, forbidden −3, escalated-answerable 0, correct escalation +1, unsafe selection −3.
* Family-clustered bootstrap (2000 resamples) for every interval; observations within a family are related, so the effective sample is ~43 families, not 172 cases.
* **Disclosed limits:** model-assisted authoring and labels, **no human review was performed**; the author had seen v2 results/categories (not v3 output); the deterministic prefilter encodes facts (`primary_worker`, `previous_worker`, `interactive`, `missing`, `access`) that the dataset provides and that are only partly present in production routing — it is a *proposal* for deterministic policy, not existing production code.
* **Fixture defect found after the final run (not hidden):** 4 `dynamic_capability` families (cal v3-053, opt v3-047, **final v3-045, v3-051**) have gold that contradicts their own metadata (an "acceptable" worker is listed as missing the required capability). The frozen files were not edited. The primary results below include them; a labelled post-hoc sensitivity analysis excludes the 2 final families (§5).

## 4. Frozen-final results (43 families, described variant, answerable semantic decisions n=324; 95 % family-cluster CI)
| System | Acceptable | Forbidden | Counter-prior | Utility/decision | Order-consistent | Swap-all follows-label | Gates passed (G1–G7) |
|---|---|---|---|---|---|---|---|
| Null (escalate all) | 0 | 0 | 0 | +0.047 | – | – | – |
| first / last (bare) | .543 [.489,.603] | .222 | .520 | −0.482 | 0.0 | – | – |
| label-prior (bare) | .537 [.438,.635] | .185 | .409 | −0.424 | .50 | – | – |
| random (bare) | .503 [.430,.580] | .225 | .500 | −0.565 | .46 | – | – |
| **Deterministic prefilter + policy order** | .667 [.545,.786] | **0** | .575 | +0.412 [.19,.63] | .658 | .730 | 4 |
| Laya-MLX (existing baseline) | .540 [.442,.639] | .225 | .453 | −0.494 | .559 | .811 | 2 |
| **Open-Jev baseline (shipped)** | .568 [.454,.675] | .173 | .504 | −0.341 [−.78,.05] | 1.0 | .628 | **3** (G1,G4,G6) |
| Open-Jev + prefilter | .691 [.580,.795] | **0** | .622 | +0.459 | .947 | .547 | 6 (fails G7) |
| Open-Jev optimised scoring (alias) | .648 [.520,.775] | .161 | .669 | −0.165 | 1.0 | .426 | 7 (but 16 % forbidden) |
| **Optimised hybrid (alias + prefilter)** | **.759 [.631,.869]** | **0** | **.764 [.63,.88]** | **+0.588 [.38,.78]** | .947 | .378 | 7 |
Gate thresholds are the unchanged R3.2C Phase 2A G1–G7. G6 uses `bench.json` (p95 657 ms, 6868 MB ≈ 6.7 GiB footprint peak) — passes narrowly. The hybrid's G7 (abstention precision) is exactly **0.50 = the threshold**.

Paired family-bootstrap deltas (acceptable; CI): hybrid − shipped Open-Jev **+0.191 [+0.017, +0.349]**; hybrid − Laya +0.219 [+0.071,+0.368]; alias − baseline +0.080 [−0.039,+0.195]; **hybrid − deterministic prefilter +0.093 [−0.043, +0.244] (positive in 90 % of resamples; utility +0.176 [−0.085,+0.465])**; Open-Jev+prefilter − deterministic +0.025 [−0.044,+0.099]; shipped Open-Jev − Laya +0.028 [−0.093,+0.144].
Post-hoc sensitivity excluding the 2 inconsistent final families: det .701, Laya .552, Open-Jev .545, Open-Jev+pf .727, alias .643, **hybrid .799 [.683,.900]** (forbidden 0 for all +pf systems).

### What the numbers say
1. **The shipped Open-Jev does not reproduce its v2 "7/7" on fresh scenarios**: 3/7, 17 % forbidden choices, 0/32 on review independence (it picks the author as reviewer), 0/16 escalation without abstention, follows the label 63 %. The v2 pass was fragile, as the bootstrap in R3.2G suggested.
2. **Most of the gain is deterministic policy, not the model.** The prefilter alone removes every forbidden choice and lifts .568 → .691 (Open-Jev) or yields .667 with a plain policy order. Review independence, worker failure/unavailable, locality and no-capable-worker escalation are *facts*, and the model is wrong on them (it gets 32 forbidden review-independence picks).
3. **Neutral aliasing helps, modestly** (+0.08 acceptable; counter-prior .504 → .669; real-vs-misleading label gap closes; swap-all follows-label .63 → .43), but its interval includes 0 and it changed coding-intent accuracy not at all (coding_testing 20/40 for both the hybrid and the deterministic baseline, i.e. no better than a coin flip on role-intent tasks). Where the hybrid beats deterministic order: background escalation (16/16 vs 4/16) and adversarial/injection families (26/28 vs 10/28) — cases a *better deterministic rule set* might also solve; no keyword/role rule classifier was built, so "model vs a good rule classifier" is **NOT MEASURED**.
4. **Ensemble (raw+alias) = no benefit over alias at twice the calls** (pooled utility tie on cal+opt; cheaper alias chosen).
5. **Calibration and abstention do not make the confidence trustworthy.** Raw confidence ECE 0.38–0.53 (it is not a probability). Platt/isotonic fitted on cal cut ECE to 0.03–0.14 on final, but mostly by regressing to the base rate; the Platt slope for the hybrid was *negative* on cal (AUROC 0.25 after mapping) while the raw score ranks correctness on final (AUROC 0.75; top-50 % by confidence → 85.7 % accurate). The relationship flips between partitions ⇒ unstable. A threshold tuned on cal never beat tau=None on opt, so none was adopted. Abstention through the `none_fits` candidate gives correct escalation on escalate-gold cases (shipped 1.0 / hybrid 1.0) without raising unsafe selections, but its precision on answerable cases is near the 0.5 boundary.
6. **Robustness (bench, 40 opt requests):** deterministic (30 repeats: max |Δp| = 0.0, 0 decision changes), insensitive to a trailing space (1/40 flips) and a dropped period (0/40), mildly to an appended "Thanks!" (3/40) but **brittle to upper-casing the task text (8/40 = 20 % flips)**.

## 5. Operational measurements on this Mac mini M4 (16 GiB), `bench.json`, `bench-lazy.json`
| | Open-Jev scorer |
|---|---|
| Cold start (first decision) | **11.3 s** (model load 9.2 s + warm-up 0.6 s; earlier R3.2G figure 13.6 s) |
| Warm latency, 1 scoring call (n=55) | p50 **586 ms**, p95 657 ms, p99 677 ms; eval-harness described requests p50 625 / p95 876 ms |
| Ensemble (2 calls, n=40) | p50 1142 ms, p95 1285 ms |
| Memory | footprint 6087 MB after the first decision → 6480 → **6868 MB peak (≈6.7 GiB)** (RSS only 0.4–0.8 GiB: weights are memory-mapped); system free memory 70 % idle → 30–41 % loaded; during long runs it fell to 23–28 % and macOS swap used grew to 6.7 of 8.2 GB — a ~6.7 GiB model is **not comfortable beside Hermes/browsers on 16 GiB** |
| Lazy lifecycle (`--idle-exit-seconds 6`) | process exits when idle (system free memory back to 75 %); the next decision after idle costs **8.8 s** (restart). Lazy loading saves memory but is unusable for synchronous routing; at best an asynchronous shadow worker |
| Laya-MLX for contrast | p95 ≈ 14 ms, ~1.1 GiB (R3.2G bench) |
A memory guard was added to the research client after the first dev run slowed under swap; it aborts rather than degrading the host.

## 6. Alternatives (no weights downloaded; unavailable comparisons are NOT MEASURED)
* **Decider-MLX, Kev-MLX: NOT MEASURED on v3.** Their runtime venv and weights are no longer on disk (`state/runtime/decider-mlx`, `kev-mlx` contain only sources/pin files). Historical R3.2C numbers on **different** v1 sets (not comparable to v3, not rerun): dev-v1 acceptable Decider .825 (forbidden .117), Kev .740 (0), Open-Jev .870 (0), Laya .649 (.149); held-out-v1 Decider .731, Kev .662, Open-Jev .723, Open-Jev-masked .646, Laya .685.
* **SemIf-OpenJev: NOT MEASURED** — only named in the R3.2C candidate review; never installed.
* Existing Laya was re-measured on v3 (cal .607, opt .588, final .540; 22 % forbidden): consistently the weakest model baseline.

## 7. Assessment
* **Open-Jev-2B as shipped: NO-GO** (fails G2, G3, G5, G7 on fresh frozen data; 17 % forbidden choices; ~6.7 GiB; 11 s cold start; brittle to casing).
* **Optimised hybrid: SHADOW-ONLY at most — not approved, not started.** Passes all 7 gates with 0 forbidden choices and the best point estimates, but (a) most of the benefit is attributable to the deterministic prefilter, (b) the hybrid-vs-deterministic advantage is not significant (CI −4 … +24 points), (c) role-intent accuracy is a coin flip, (d) G7 sits on its boundary, (e) labels are model-assisted with a disclosed fixture defect, (f) 0.6 s and ~6.7 GiB per decision on the always-on host.
* Conditions before any shadow run: human-reviewed v3-style labels (and the 4 inconsistent families fixed in a new version, not in place); a decision on a memory lifecycle (shadow worker on demand, never beside the control plane under pressure); the prefilter implemented and tested as deterministic policy *first* (it has value without any model); an opt-in shadow log that cannot affect routing.
* **Highest-value follow-up independent of Open-Jev:** implement the deterministic prefilter facts (reviewer ≠ author, failed-worker hand-off, interactive vs background-only, subscription-first cost, capability-missing, high-risk-without-approval) in the router's own eligibility layer and measure a keyword/role classifier against the model.

## 8. Reproduce / evidence
`audit/openjev-v3/{dev,cal,opt,final}/*.json` (per-system results with per-decision records), `selection.json`, `freeze.json`, `final-prerun.json`, `report.json`, `bench.json`, `bench-lazy.json`, `order-sensitivity.json`. Score cache `state/openjev-opt/cache.jsonl` (git-ignored). Tests: `uv run pytest evals/test_openjev_opt.py`.
