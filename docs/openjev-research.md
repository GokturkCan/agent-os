# Open-Jev-2B research outcome (R3.2H) — what is decided, what is not

**Decision (unchanged by integration):** shipped Open-Jev = **NO-GO**. Existing Laya-MLX = **NO-GO** (weakest model baseline; `candidate` status).
The optimised hybrid (neutral aliases + deterministic prefilter) = **SHADOW-ONLY research candidate, not approved, not started.**
Production stays `NullBackend`, `tiers.fastgate.model: null`, empty `activation.*` allowlists. Deterministic policy comes first.

Full analysis: `audit/openjev-v3-closure-2026-10-18.md`. Evidence retention and verification: `audit/openjev-v3/EVIDENCE-RETENTION.md`.

## What the numbers do and do not show (frozen final, 43 families, 324 answerable decisions)
* Hybrid acceptable .759 [.631, .869], forbidden 0; deterministic prefilter + policy order .667 [.545, .786], forbidden 0.
* **The hybrid is NOT shown to be better than the deterministic prefilter:** paired delta +0.093 acceptable, 95 % family-cluster CI **[−0.043, +0.244]**
  (positive in 90 % of resamples); utility +0.176 [−0.085, +0.465]. The interval crosses zero. Most of the gain is deterministic policy facts
  (reviewer ≠ author, worker unavailable, locality, no capable worker), not the model.
* "Model vs a good keyword/role rule classifier" was **not measured**. Decider/Kev/SemIf were **not measured** on v3 (weights/runtimes not on disk; nothing downloaded).
* The hybrid's abstention precision (G7) sits exactly on the 0.50 threshold. Cost: ~0.6 s per decision, ~6.7 GiB footprint, 11 s cold start on the 16 GiB Mac.

## Disclosed fixture defects (frozen files NOT edited)
Four `dynamic_capability` families have gold that contradicts their own option metadata (an "acceptable" worker is listed as missing the required
capability): cal `v3-053`, opt `v3-047`, **final `v3-045`, `v3-051`**. They were found after the final run. The primary results include them.
A labelled **post-hoc** sensitivity excluding the two final families (`report.json: final_excluding_inconsistent_families_POST_HOC`):
deterministic .701, shipped Open-Jev .546, Open-Jev+prefilter .727, hybrid .799 [.683, .900]. The ordering and the "interval overlaps the
deterministic baseline" conclusion are unchanged; the defect does not rescue the model-only systems. A corrected set must be a NEW version (v4) with
human-reviewed labels, never an in-place edit.

## Where the code lives
Research-only, model-launching code is **outside the production package**: `scripts/openjev/{openjev_opt,openjev_scorer,run_study,analyse,report,bench,lazy,order_sensitivity,author_v3,evidence}.py`.
Nothing under `agentos/` imports it, it is not in `systemone.BACKENDS`, `config/systemone.yaml` or routing (pinned by `evals/test_openjev_opt.py`).
The v3 datasets (`evals/data/openjev-v3-*.yaml`) are protected policy files (`evals/**`).

## Conditions before any shadow run (from the closure; none met)
Human-reviewed v3-style labels incl. a fixed v4 of the four families; a memory-lifecycle decision; the deterministic prefilter implemented and tested
as router eligibility policy first; an opt-in shadow log that cannot affect routing; separate human approval of any `activation.*` change.
