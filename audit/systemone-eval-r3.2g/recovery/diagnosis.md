# Phase 1 diagnosis (2026-10-14)

- Initial sandbox full suite: 36 failures, 669 passes, 2 skips. uv cache access,
  Metal startup and process/RSS inspection were restricted. Preserve this run;
  it is not a model quality result.
- Initial host full suite: 9 failures, 696 passes, 2 skips. Seven failures share
  exactly one root cause: new evaluation files were not represented in the
  protected manifest. Two dispatch failures record `No such file or directory:
  python` in their isolated task findings. Running with the existing repository
  venv on PATH resolves that environment defect without changing tests.
- Initial sandbox health: 2 FAIL, 3 WARN. Protected manifest drift plus uv cache
  denial in canonical entrypoint. Host validation uses the same existing venv.
- Platt: unbounded Newton update overshot, causing exp(-logit) overflow on the
  saved B2-raw development records. Stable piecewise sigmoid, stable logistic
  loss, tiny ridge and backtracking replace unconstrained Newton updates. Both
  fitting and application are safe for extreme logits. Offline only.
- Isotonic already pooled tied confidence values. Rounding x boundaries to six
  decimals could misassign nearby values; preserve exact x boundaries. Tests
  verify permutation invariance, ties, pooling, endpoints and close confidences.
- G7 reported mismatch is NOT present in the recovered source/results. Both use
  `precision_of_abstention_on_escalate_gold`. No fabricated key migration.
  Missing/nonfinite measurements now produce UNKNOWN with pass=null.
- G6 formerly treated absent memory as PASS and eval p95 as warm benchmark.
  Missing either benchmark or memory now yields UNKNOWN (a measured threshold
  failure still yields FAIL). Original thresholds remain unchanged.
- Manifest refresh records mechanical candidate hashes ONLY, explicitly pending
  human review before merge. Exact before/after hashes are in protected-delta-*.json.
  No production config or historical R3.2C/F files were edited.
