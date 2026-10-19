# Run 3 protected-file approval packet (against `main` fffc3a1)

**Status: approval PENDING. Nothing here is, or may be read as, a recorded human approval.** The protected manifest was regenerated mechanically
(`agentos manifest --write`) from the integrated tree; a matching manifest proves only that the files are what this packet lists.
Machine-readable delta with full hashes, purposes and effects: `audit/run3-final-protected-delta.json`.

Delta: **38 added + 2 modified protected files, 0 removed** (manifest 39 → 77 entries), plus `evals/protected-manifest.json` itself
(not self-listed). Supersedes the PR #3 packet (23 entries) and the sibling-branch deltas (#4, #5, #6).

## A. Files that decide policy (read these)
| Path | St | sha256 old → new | Class |
|---|---|---|---|
| `agentos/permissions.py` | M | `92b214644de0` → `79a2ee98cffd` | narrowing |
| `config/compute.yaml` | A | `—` → `912979050971` | fail-closed |
| `config/systemone.yaml` | A | `—` → `ad4fc1751893` | fail-closed |
| `evals/test_hermes_integration.py` | M | `8df503be8fb9` → `8091a47d9982` | test-only |

* `agentos/permissions.py` — `git diff origin/main HEAD -- agentos/permissions.py`: adds only `config/systemone.yaml` and `config/compute.yaml` to `PROTECTED_POLICY_PATHS`. **No permission, grant, profile or `never_grantable` entry changed. No broadening.**
* `config/systemone.yaml` — 5 backend definitions (argv = runtime venv python + worker script) that name executables; `activation.production_backends: []`, `activation.fastgate_models: []`.
  The workers (`agentos/systemone_workers/*`), the adapter and the router/config guards are **unprotected code**: their integrity rests on the protected tests (mutation-checked in the PR #3 review).
* `config/compute.yaml` — `nodes.msi: enabled false, endpoint_ref null, auth_ref null`; `offerings: {}`; `authorizations: []`. Refs are symbolic (validated: no URL/IP/credential). `config/resources.yaml` may no longer carry a `compute` block (validate rejects it).
* `evals/test_hermes_integration.py` — test-only change (see class column); no assertion weakened.

## B. Evaluation data, authoring scripts and tests (gate evidence)
| Path | St | sha256 old → new | Class |
|---|---|---|---|
| `evals/data/author_retrieval_suite.py` | A | `—` → `9691d3ed94e8` | data-only |
| `evals/data/modules/author_context_suites.py` | A | `—` → `05cc3248d65e` | data-only |
| `evals/data/modules/author_efficiency_suites.py` | A | `—` → `ec7fe5fcb4d8` | data-only |
| `evals/data/modules/author_wakegate_suite.py` | A | `—` → `5f6e46a01aa0` | data-only |
| `evals/data/modules/contextgate-suite-v1.yaml` | A | `—` → `7dda050b0e0b` | data-only |
| `evals/data/modules/contextgate-suite-v2-dev.yaml` | A | `—` → `36003ee999fe` | data-only |
| `evals/data/modules/contextgate-suite-v2-holdout.yaml` | A | `—` → `8e74f4777d4c` | data-only |
| `evals/data/modules/toolpruner-suite-v1.yaml` | A | `—` → `72ebb1df2b00` | data-only |
| `evals/data/modules/toolpruner-suite-v2-dev.yaml` | A | `—` → `e775e74e54dc` | data-only |
| `evals/data/modules/toolpruner-suite-v2-holdout.yaml` | A | `—` → `41aec3e022c7` | data-only |
| `evals/data/modules/wakegate-suite-v1.yaml` | A | `—` → `c505146d237a` | data-only |
| `evals/data/modules/wakegate-suite-v2-dev.yaml` | A | `—` → `18d4b6a5c98b` | data-only |
| `evals/data/modules/wakegate-suite-v2-holdout.yaml` | A | `—` → `976691333df6` | data-only |
| `evals/data/openjev-v3-cal.yaml` | A | `—` → `a5aa118fd7f6` | data-only |
| `evals/data/openjev-v3-final.yaml` | A | `—` → `c707921a14c5` | data-only |
| `evals/data/openjev-v3-opt.yaml` | A | `—` → `c6318e695614` | data-only |
| `evals/data/retrieval-suite-v1.yaml` | A | `—` → `79314892c26f` | data-only |
| `evals/data/systemone-decisions-v1.yaml` | A | `—` → `30e211a6ea92` | data-only |
| `evals/data/systemone-heldout-v1.yaml` | A | `—` → `3affe3b44a17` | data-only |
| `evals/data/systemone-heldout-v2.yaml` | A | `—` → `c35d90cd91c1` | data-only |
| `evals/test_compute_contract.py` | A | `—` → `747a0fefce6e` | test-only |
| `evals/test_efficiency_patterns.py` | A | `—` → `9491451bb33b` | test-only |
| `evals/test_laya_smoke.py` | A | `—` → `347c60d6a49b` | test-only |
| `evals/test_openjev_opt.py` | A | `—` → `62fb94f7d86d` | test-only |
| `evals/test_r32g_modules.py` | A | `—` → `506dfacf6b21` | test-only |
| `evals/test_r32g_recovery.py` | A | `—` → `194d8735e51d` | test-only |
| `evals/test_run3_invariants.py` | A | `—` → `8461d0534842` | test-only |
| `evals/test_systemone_activation.py` | A | `—` → `aab9be2cc101` | test-only |
| `evals/test_systemone_adapter.py` | A | `—` → `856ac3073401` | test-only |
| `evals/test_systemone_bench.py` | A | `—` → `8eda241f5ca1` | test-only |
| `evals/test_systemone_eval.py` | A | `—` → `a358791becac` | test-only |
| `evals/test_systemone_heldout.py` | A | `—` → `c189a0397156` | test-only |
| `evals/test_systemone_heldout_v2.py` | A | `—` → `dbfaaf84f733` | test-only |
| `evals/test_systemone_options.py` | A | `—` → `5b627e6f9d08` | test-only |
| `evals/test_systemone_pipeline.py` | A | `—` → `1a231480ac7f` | test-only |
| `evals/test_systemone_routing.py` | A | `—` → `6e2016626e5f` | test-only |

Data files are model-assisted (no human review, disclosed in each file's provenance); the three `openjev-v3-*` files are frozen (`audit/openjev-v3/freeze.json`) and contain 4 disclosed defective families that are documented, not edited (`docs/openjev-research.md`).

## C. Security-relevant but NOT protected (review separately)
`agentos/router.py` + `agentos/config.py` (activation guards), `agentos/systemone_adapter.py`, `agentos/systemone_workers/*`, `agentos/compute.py`, `agentos/compute_jobs.py`, `agentos/hermes_bridge.py`, `agentos/cli.py` (research subcommands take an explicit backend; they never edit `activation.*`), `.github/workflows/ci.yml`.
Recommendation (not done, needs your decision): add the adapter, workers and guard modules to `PROTECTED_POLICY_PATHS` before any activation discussion.

## D. Verified invariants (tests: `evals/test_run3_invariants.py`, `evals/test_systemone_activation.py`, `evals/test_compute_contract.py`)
SystemOne backend `null` · `tiers.fastgate.model: null` · both allowlists `[]` · Laya `candidate` (not in USABLE) · MSI compute disabled · offerings/authorizations empty · no network/SSH client in `compute*.py` ·
research model-launching code lives in `scripts/openjev/` (nothing in `agentos/` imports it) · ContextGate/ToolPruner/WakeGate/retrieval/rule-cache imported only by the opt-in `module_eval` · Hermes disable list intact · no private absolute paths or weights in tracked source.

## E. Inspect
```
git diff origin/main HEAD -- agentos/permissions.py config/routing.yaml config/models.yaml config/resources.yaml
git show HEAD:config/systemone.yaml ; git show HEAD:config/compute.yaml
git diff origin/main HEAD -- evals/test_hermes_integration.py
git diff origin/main HEAD -- agentos/router.py agentos/config.py agentos/hermes_bridge.py
uv run agentos manifest && uv run agentos validate
uv run pytest -q evals/test_systemone_activation.py evals/test_run3_invariants.py evals/test_compute_contract.py evals/test_policy_protection.py
```
## F. Approval checklist (yours; record it outside the manifest)
- [ ] A: `permissions.py` adds only the two paths; `systemone.yaml` and `compute.yaml` fail closed as listed.
- [ ] A: you accept guards/adapter/workers being unprotected for now (or order them protected first).
- [ ] B: you accept the model-assisted data and the disclosed defective families as evidence, not ground truth.
- [ ] `evals/test_hermes_integration.py` change is acceptable.
- [ ] You ran section E.
- [ ] Then, and only then, decide approval of the whole delta (all-or-nothing is simplest; the delta cannot be split without re-planning).
