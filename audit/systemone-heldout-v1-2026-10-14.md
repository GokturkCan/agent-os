# SystemOne held-out set v1 — freeze record (R3.2C Phase 2B)

| Field | Value |
|---|---|
| File | `evals/data/systemone-heldout-v1.yaml` (dataset id `systemone-heldout-v1`) |
| sha256 (frozen) | `3affe3b44a1734357f32a5675540f9dedf9d6802715385f6607c7c781b2e6253` |
| Frozen | 2026-10-14, at commit B of the R3.2C execution session, **before** any Strands Decider or Kev output and before any Laya run on this set |
| Development set (unchanged) | `evals/data/systemone-decisions-v1.yaml` sha256 `30e211a6ea922d6ad0ae7f1a5a65a5719a8c213efb8168f48fc991d4e7412396` (66 cases, 12 e2e) |
| Composition | 64 cases (60 semantic, 4 policy), 149 scored option orderings per variant; EN 33 / TR 31; 10 escalation-gold; 6 Layer-3 e2e cases |
| Categories | coding_testing 12, dynamic_capability 7, label_bias 6, escalation 5, description_bias 4, interactive_constraint 4, locality_cost 4, review_independence 4, invalid_options 3, approval_boundary 2, background_escalation 2, equally_acceptable 2, insufficient_info 2, risk_routing 2, unavailable_worker 2, worker_failure 2, single_option 1 |
| Guard | `evals/test_systemone_heldout.py::test_heldout_is_the_frozen_file` pins the sha256; the file is under the protected `evals/**` manifest |

## What is new relative to the development set
* **Free text instead of the `need` signal** (EN and TR summaries ≤ 200 chars): the backend must infer the need.
* **Neutral and misleading option ids** (`w_alpha`, `test_writer`, `quick_fixer` …) carrying a real worker's exact config metadata — separates label reliance from description reliance.
* Dynamic capability sets checked against the registry, reviewer independence with aliases, approval-granted high-risk cases (escalating there is safe but not a success), worker failures, unavailable status, empty / invalid option ids, ambiguous and insufficient-information cases.
* Generalized description-swap probe (`description_swap_all`) over every two-option answerable case.

## Annotation, provenance, independence
Guidelines and provenance are in the YAML header. Labels derive only from cited config facts; deterministic checks
(`evals/test_systemone_heldout.py`) verify capability gaps against the registry, the reviewer rule, risk gate, GPU
class, interactive constraint, alias metadata equality and Layer-3 expectations. All checks passed on the first run;
**no label was edited after authoring.** Limitation: no independent human annotator has reviewed the set yet.

## Reference baselines on the frozen set (bare variant; deterministic choosers, not candidates)
| Baseline | acceptable | forbidden | counter-prior | escalation-gold | EN | TR |
|---|---|---|---|---|---|---|
| first | 0.5615 | 0.1692 | 0.4444 | 0.0 | 0.5606 | 0.5625 |
| last | 0.5615 | 0.1692 | 0.4444 | 0.0 | 0.5606 | 0.5625 |
| label-prior | 0.6154 | 0.0923 | 0.3056 | 0.0 | 0.6515 | 0.5781 |
| random (seed 1337) | 0.5846 | 0.1769 | 0.4444 | 0.0 | 0.5909 | 0.5781 |

Evidence: `audit/systemone-eval-r3.2c/heldout/baseline-*.json`. Command:
`uv run agentos systemone-eval --backend baseline:<kind> --dataset heldout --out …`.

## Usage rule
Each candidate is scored once on this file with its adapter and prompt template frozen beforehand. No prompt, template,
threshold, model or variant choice may be tuned on held-out results.
