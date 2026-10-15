# R3.2G recovery checkpoint

Base HEAD e2b1967, branch feature/run3-local-intelligence. Original dirty work retained.
User authorized completion and local commits, no push/merge/activation/downloads.
2026-10-14: user confirmed previous Claude session stopped. Process inspection found
idle Claude parent/spares, no repository open file handles except cwd, no separate
model benchmark. Do not terminate those unrelated processes.

Phase 1 active. Initial sandbox run: 36 failed, 669 passed, 2 skipped; additional
failures arise from uv cache / Metal / process access restrictions. Initial host run
is in recovery/initial-host-regression.log. Health sandbox: manifest drift plus uv
restriction. Seven new protected eval files cause manifest drift (not config drift).
Platt overflow reproduced using dev/B2-raw.json; original traceback retained.
Current G7 key matches evaluator and stored results; investigate missing evidence
semantics, not an assumed rename. G6 incorrectly accepts absent memory measurement.

Existing dev/module JSON files are historical and must not be overwritten. v2 has
NOT been authored/frozen/scored. Next: stabilize numerical calibration and gate
reporting, validate tests/manifest review diff, then finish modules, ablations,
blinded fresh-context review and committed v2 freeze before inference, comparable
benchmarks and final closure. Production null defaults remain mandatory.

Phase 1 complete: recovery/stabilized-regression.log = 713 passed, 2 skipped;
recovery/stabilized-health.log = 0 FAIL, 3 WARN. PATH must include .venv/bin and
model/host tests require elevated sandbox access for Metal, uv and RSS inspection.
Phase 2 edge cases fixed: error/abstention conflicts, exact CRLF recovery + hash
integrity, exact task-state cache scope, approval/error events outside alert kind,
security/path protection in pruner, reserved compat IDs, acceptance CLI exit status.
Focused suite now 50 passing tests. No weakened assertions or original gate changes.
Dev rerun ongoing via scripts/r32g/run_development.py (sequential); preserve files.
v2 authored, 128 cases (32 families x language x label representation), NOT frozen
or scored. Fresh-context blinded reviewer working on v2-blinded-review.json only.
Two E2E expected status names corrected against router before freeze; gold case
labels unchanged. v2 deterministic checks: 4 passed.
Next run scripts/r32g/run_performance.py AFTER development completes; one heavy
model at a time. Then select candidate using prereg rules, adjudicate blinded
review, full validation and local implementation commit; commit v2 freeze with
exact hashes before inference. Existing JSON evidence hashes recorded.
