# Run 3 release candidate — handoff and the single decision

**Branch:** `integration/run3-final` → Draft PR to `main`. **Supersedes** stacked PRs #3 (SystemOne/R3.1–R3.2G), #4 (compute contract CN-1),
#5 (efficiency R3.5) and #6 (Open-Jev R3.2H); those branches and their history are untouched and still reproduce each stage independently.
(#4–#6 are stacked on #3's earlier head; merging this PR makes them redundant — close them afterwards, do not merge them.)

## What is in it
SystemOne wiring + adapter + evaluations (null by default) · compute-node contract (disabled, empty) · efficiency modules (opt-in, unwired) ·
Open-Jev closure (NO-GO; hybrid shadow-only) · Hermes archived-skill fix · fail-closed analysis/evidence archive · minimal offline CI · invariants test.
Details: `CHANGELOG.md`, `CURRENT_STATE.md`, `docs/roadmap.md`, `docs/openjev-research.md`, `docs/compute-contract.md`, `docs/efficiency-patterns.md`, `docs/ci.md`.

## Not in it / explicitly out of scope
No neural backend activated; no model downloaded; no MSI execution, SSH path or node; no Hermes live-config or live-skill change; no human approval recorded;
no tag/release; PRs #3–#6 not closed or retargeted.

## The one decision required
Approve (or reject) the protected-file delta in `docs/run3-protected-approval-packet.md` (40 files + manifest). If you approve: record it outside the manifest
(e.g. a signed comment on the PR), then merge. If not: nothing merges; list the files to change.

## Residual caveats
* CI is minimal and not a security approval; 8 host-dependent tests and the real-model smoke run only locally (`docs/ci.md`). GitHub Actions has not yet run for this branch (first run happens on the PR).
* Adapter, workers and activation-guard code are unprotected (packet §C).
* Datasets are model-assisted; 4 Open-Jev families are defective (documented).
* The GitHub MCP token is rejected (HTTP 401; host state, unrelated); `gh` CLI worked for pushes/PRs.
* Optional human actions: publish the evidence archive as a GitHub release asset; protect the adapter/guard modules; close PRs #3–#6 after merge.
