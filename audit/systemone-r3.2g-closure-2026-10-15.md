# R3.2G closure — lightweight Laya pipeline, Open-Jev-2B on fresh v2, and opt-in modules (2026-10-15)

**Result: the lightweight Laya pipeline FAILS the original G1–G7 on v2 (3/7). Open-Jev-2B passes 7/7 on v2, but that pass is narrow,
statistically fragile, contradicted by its own v1 result, and rests on a model-assisted (not human) reviewed set. NullBackend stays;
nothing is activated.** R3.2C/R3.2F evidence and gate definitions are untouched.

Commits (branch `feature/run3-local-intelligence`): `e2b1967` ecosystem review + preregistration · `9598de9` implementation, dev ablations,
module evidence · `75e919d` **v2 freeze (before any v2 inference)** · closure commit listed in the final report. Not pushed.
Production defaults verified unchanged: `systemone.backend: "null"`, `fastgate` model null (`config/` untouched in R3.2G).

## 1. v2 freeze ordering (contamination check)
* `evals/data/systemone-heldout-v2.yaml` sha256 `c35d90cd91c1c855102fa05f9ad0054c6d8086e40bed40a77472871e5e2026cc` = value in `v2-freeze.json`
  and in the protected manifest. Committed at `75e919d`; `v2/inference-start.json` records that exact commit and was written by
  `scripts/r32g/run_v2.py` only after it asserted the committed bytes equal the frozen hash. Before that commit, no v2 result file existed
  anywhere in the repository (searched: no JSON with dataset id `systemone-heldout-v2` except freeze/review metadata). v2 was not edited after scoring.
* **Disclosed limitations (not hidden):** (1) v2 was authored after the development ablations had been run and seen by the author session, so
  author knowledge of dev behaviour cannot be excluded (no v2 *model output* was seen); (2) review was a fresh-context **blinded model pass, NOT human**:
  128/128 acceptable/escalation labels agreed, 48 forbidden-label differences were adjudicated by rule ("preference exclusion is not policy-forbidden",
  `v2-adjudication.json`), two e2e expected status names were corrected against the router before freeze; (3) 128 observations = **32 scenario
  families × {EN,TR} × {real, misleading labels}** — related observations, not 128 independent tasks; (4) the original G1–G7 were used as-is.

## 2. Development ablations (dev set, 66 cases / 152 answerable decisions; label-prior 0.714) — `audit/systemone-eval-r3.2g/candidate-selection.json`
| cfg | neutral | strategy | acceptable | forbidden | counter-prior | order-consistent | swap-all follows-label | G7 prec | bench p95 | RSS GiB | calls/dec | gates passed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A vanilla (wrapper = plain backend) | – | choice | 0.649 | 0.149 | 0.467 | 0.640 | 0.932 | 0.133 | 14 ms | 1.08 | 1.0 | G1 G6 |
| B1 | on | choice | 0.571 | 0.188 | 0.467 | 0.040 | 0.946 | 0.099 | 16 ms | 1.08 | 1.0 | G1 G6 |
| B2 | on | per-option | 0.571 | 0.182 | 0.422 | 1.000 | 0.540 | 0.116 | 55 ms | 1.08 | 2.27 | G1 G2 G4 G6 |
| **B2-raw (selected)** | off | per-option | **0.727** | 0.130 | 0.600 | 1.000 | 0.730 | 0.071 | 52 ms | 1.08 | 2.27 | G1 G3 G4 G6 |
| B3 | on | consistency | 0.039 | 0.000 | 0.022 | 0.040 | 0.027 | 0.115 | 42 ms | 1.08 | 2.02 | G1 G2 G6 (escalates 96%) |
| B3-raw | off | consistency | 0.442 | 0.058 | 0.289 | 0.640 | 0.784 | 0.118 | 44 ms | 1.08 | 2.06 | G1 G6 |
| Null | – | – | 0.000 (escalates all) | 0 | – | – | – | – | – | – | 0 | – |
Component attribution (dev, ON/OFF): per-option scoring is what produced order invariance (G4 0.64→1.00) and +0.08 acceptable; **neutral aliasing did not help and hurt**
(B2 vs B2-raw: 0.571 vs 0.727; B1 vs A: 0.571 vs 0.649 — option ids carry usable signal in the metadata-less cases and aliasing also breaks id mentions in state text);
consistency checking mostly converts decisions into escalations. Selection followed the preregistered rule (G1+G6 required, most G2/G3/G4/G5/G7 passes, then acceptable, then fewer calls). Dev results never used to claim generalisation.

## 3. Frozen v2 comparison (`audit/systemone-eval-r3.2g/v2/*.json`, `v2-report.json`; label-prior baseline on v2 = 0.615)
| | A vanilla Laya | **C selected Laya pipeline** (`pipeline:laya-mlx:raw:per-option`) | **D Open-Jev-2B** | first / last / label-prior / random | Null |
|---|---|---|---|---|---|
| acceptable (described) | 0.567 | 0.644 | **0.721** | 0.577 / 0.577 / 0.615 / 0.596 | 0 (escalates) |
| EN / TR | 0.519 / 0.615 | 0.615 / 0.673 | 0.731 / 0.712 | | |
| forbidden-choice rate | 0.298 | 0.231 | 0.115 | 0.269 / 0.269 / 0.211 / 0.260 | 0 |
| counter-prior acceptable (G3 ≥ 0.60) | 0.493 | 0.562 | 0.644 | | |
| swap-all follows-label (G2 ≤ 0.60) | 0.825 | 0.690 | 0.580 | | |
| order-consistent (G4 ≥ 0.80) | 0.570 | 1.000 | 1.000 | | |
| acceptable − label-prior (G5 ≥ +0.05) | −0.048 | +0.029 | +0.106 | | |
| abstention precision / recall (G7 ≥ 0.5) | 0.079 / 0.625 | 0.060 / 0.250 | 0.889 / 1.000 | | |
| acceptable with abstain exposed | 0.288 | 0.466 | 0.721 | | |
| e2e routing cases | 3/3 | 3/3 | 3/3 | | |
| model calls / decision | 1.0 | 1.98 | 1.0 *(N candidate sequences)* | | |
| **G1 G2 G3 G4 G5 G6 G7** | P F F F F P F (2/7) | P F F **P** F P F (3/7) | **P P P P P P P (7/7)** | | |
Per category (answerable semantic, described; A / C / D): background_escalation .875/.75/.50 · coding_testing .54/.58/.67 · dynamic_capability .53/.60/1.0 · interactive_constraint .38/.75/1.0 ·
label_bias .57/.64/**.36** · locality_cost .13/.25/1.0 · research_docs .75/.50/1.0 · **review_independence .38/.50/0.0** · unavailable_worker .38/.50/1.0 · worker_failure .44/.75/.50 ·
approval_boundary and escalation 0/0/0 (escalate-gold: any selection is wrong; correct only via abstain) · conflicting_info, equally_acceptable, insufficient_info, single_option 1.0 for all.

**Uncertainty (post-hoc, descriptive, did not alter any verdict) — cluster bootstrap over the 32 families, `v2-bootstrap.json`:**
Open-Jev-2B acceptable 95% CI 0.53–0.81; **G5 delta CI −0.009…+0.21 (delta ≥ 0.05 in 80% of resamples)**; **G3 CI 0.50–0.81 (≥ 0.60 in 72%)**; G2 0.580 passes by 0.02.
Selected Laya pipeline: acceptable CI 0.50–0.69, G5 ≥ 0.05 in 34% of resamples, G3 ≥ 0.60 in 24%.

## 4. Answers to the closure questions
1. **Lightweight Laya pipeline, all gates on v2?** No: 3/7 (G1, G4, G6). It fixes order consistency (0.57→1.00), reduces forbidden choices (0.30→0.23) and moves acceptable +0.08 over vanilla, but G2 (0.69), G3 (0.56), G5 (+0.03) and G7 (0.06) fail. Per-option scoring cannot make a 322M classifier read descriptions reliably; it costs ≈2 calls/decision.
2. **Open-Jev-2B on the same workload?** 7/7 by the unchanged definitions. Not a validated pass: the same model failed G2 (0.638) and G3 (0.583) on v1 and G5/G3 are inside bootstrap noise here; it scores **0.00 on review_independence and 0.36 on label_bias**, 11.5% forbidden choices; v2 is model-assisted-reviewed with the author aware of dev behaviour.
3. **Resource/latency (bench payload, M4 16 GB, `performance/`):** Laya vanilla p50/p95/p99 12.9/14.4/14.7 ms, cold 0.83 s, RSS 1.08 GiB, 76 dec/s. Selected pipeline 32/52/56 ms, cold 0.49 s, RSS 1.08 GiB (footprint 1.5 GiB), 32 dec/s, 1.94–2.27 calls. Open-Jev-2B 418/613/662 ms, cold 13.6 s, RSS 0.84 GiB but **physical footprint 6.4 GiB; system-free memory fell to 37% while loaded**, 2.9 dec/s. Pipeline p95 > 100 ms target? No (52 ms) and memory < 1.5 GiB? RSS yes (1.08), footprint 1.54 GiB marginally no. Rich eval requests are slower than bench payloads (Open-Jev described p95 ≈ 0.9–1.3 s in earlier R3.2F runs). Open-Jev is ≈ 12× slower and ≈ 4× larger than the pipeline for a +0.08 acceptable / G2–G7 advantage.
4. **Modules with independently measured value (synthetic author-written suites, token counts = ceil(chars/4) estimates):**
   * **ContextGate, deterministic (model OFF): 0/35 essential facts lost, exact recovery, 50.7% reduction, 4 ms/transcript — the clear winner.** Laya-assisted: 59.4% reduction, 0/35 lost, but 55 model calls, p50 80 ms (max 636 ms) for +8.7 points; the first deterministic run lost 4/35 and was fixed (tail/protected-line retention) — first-run artifacts preserved.
   * **Tool-result pruner: 0/27 essential lines lost, exact recovery, 46.1% reduction deterministic**; the Laya path makes 0 calls on this suite after the safety fixes (earlier 2/27 loss with the model and 63.9% deterministic reduction before the path/security protections). The model adds nothing measurable here.
   * **WakeGate: deterministic rules 0 missed important events, 14 unnecessary wakes of 18 should-defer cases, only 4/46 turns avoided; Laya-assisted avoids 7 but missed 1 important event → acceptance FAILED.** Value is the rules, not the model; savings are small.
   * **Rule cache: behavioural suite passes** (nothing applies before named-human approval, exact scope, config-change invalidation, never adds an option, revocation). Caller-controlled prototype, not authentication; no rule approved.
   * Offline calibration (fit on dev records of the selected pipeline, applied unchanged to v2 C): raw ECE 0.287 (dev) / 0.240 (v2), Brier 0.278, AUROC 0.58 / 0.57 — the raw score barely separates right from wrong; Platt cut v2 ECE to 0.126, isotonic to 0.222. This makes the score more honest about its own accuracy; it does not change which worker is chosen and cannot fix the G2/G3/G5 failures. Platt overflow bug fixed (first failure preserved). Nothing activated; no `kind="calibrated"` anywhere (`v2-calibration-C.json`).
   * Compat adapter: function + CLI, cannot widen the policy-eligible set, escalation ids reserved; no daemon.
5. **Production NullBackend?** Yes. No pipeline or model has passed validation that would justify activation; C fails 4 gates and D's pass is unvalidated and operationally heavy (6.4 GiB, 0.4–0.6 s).
6. **Further validation strictly required before any activation (even shadow mode)?** Yes, for Open-Jev-2B specifically: a fresh **human-reviewed** set (v3) authored without sight of any outputs, ≥ 100 independent scenarios (not variants of 32), pre-registered, with `review_independence`/`label_bias` families strengthened, plus an operational decision that a 6.4 GiB model is acceptable on the always-on control plane (or an on-demand/shadow-only lifecycle). Until then V1 FastGate = deterministic C0 policy + NullBackend.

## 5. Ecosystem projects (`r3.2g-ecosystem-review-2026-10-14.md`, pins in `r3.2g-ecosystem-pins.json`)
IMPLEMENT: Jev-Calibration methodology (offline). PROTOTYPE: WakeGate, fast-jev-compaction, jev-pruner, Unclutter pattern. REFERENCE: LiteLLM, Vercel AI SDK, Pydantic AI,
jev-ultrafast, voice-browser, JevPilot, Minecraft Agent, jev-trader. REJECT/out of scope: mobile-jev (paid device API), Automaton (autonomous spending/self-replication). Nothing installed; no mandatory dependency added.

## 6. Protected-file review items (human approval: **PENDING**)
`evals/protected-manifest.json`: **10 files added, 0 modified, 0 removed, 0 `config/` files changed** — full before/after hashes in `audit/systemone-eval-r3.2g/recovery/protected-delta-final.json`
(modules suites + authoring scripts, v2 dataset, five new test files). The manifest note states the refresh is mechanical, not approval. `config/systemone.yaml` was not touched in R3.2G
(its R3.2C/F additions remain pending review from those milestones). New runtime entry points (`agentos` subcommands: `systemone-calibration`, `systemone-compat`, `module-eval`, `pipeline:` specs) are opt-in.

## 7. Known limitations
Synthetic, author-written data throughout; v2 related observations; model-assisted review only; token counts are character estimates; WakeGate/ContextGate/pruner suites measure the modules not worker-routing quality;
Open-Jev-2B ran at bf16 on MPS (no quantization); first-run/failed artifacts retained (`modules/*-run1.json`, `modules-recovery/*`, `recovery/initial-*`); one-shot v2 runner prevents re-scoring.

## 8. Recommendation
Close SystemOne/FastGate research for V1 with **NullBackend + deterministic policy**. Record Open-Jev-2B as the single credible future optional candidate (pending human-reviewed validation and a memory-lifecycle decision); drop per-option Laya as a decider; keep ContextGate/pruner/WakeGate as **deterministic-first opt-in utilities** for R3.4 context handling (model OFF by default), and the offline calibration tool for any future backend. Proceed to R3.4 local reasoning integration without a FastGate model dependency.
