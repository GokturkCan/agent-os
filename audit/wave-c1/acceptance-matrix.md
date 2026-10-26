# Wave C1 — eight production acceptance gates

Rule for this document: **a gate is PASS only with evidence that exists and can be re-run.** Statuses: `PASS` · `PARTIAL` (named sub-evidence exists, gate not met) · `NOT RUN` (procedure defined, never executed) · `BLOCKED` (cannot run until a named prerequisite exists).
**No gate is PASS today.** Gate 8's provenance half and gate 7's offline half have real evidence; both gates remain PARTIAL.
No additional LLM arms were run in this pass. The fixtures below are *specifications* of harder tasks; none has been built or executed.

## Common execution rule (applies to every gate that runs a worker or third-party skill script)

`audit/wave-c1/bench/tools/run_arm.sh` is **not a sandbox** and must not be run again. Gates that execute a model with Bash/Node/Python must run inside an isolation boundary with: no home-directory mount, no credentials, network egress blocked except an explicit package mirror when a gate needs `npm ci --ignore-scripts`, a writable scratch worktree only, and a wall-clock cap. Candidates on this machine: a Docker container (`docker run --network none`, binary present, daemon not checked) or a `sandbox-exec` Seatbelt profile (present, deprecated but functional). **Update:** a `sandbox-exec` profile and canaries now exist (`isolation-harness-proposal.md`; Docker is unavailable: daemon not running). They cover deterministic tool execution only; model-run isolation and browser QA are still unverified/blocked, so every gate that needs them stays **BLOCKED**, not passed.
Deny-pattern lists and tool allowlists are defence in depth and are never counted as the boundary.

## Summary

| # | Gate | Status | Evidence that exists | Blocking prerequisite |
|---|---|---|---|---|
| 1 | UI/UX design quality | PARTIAL | one run per arm, single rater, directional; **draw step not exercised** | isolation harness; blind-rated repeats |
| 2 | TypeScript/React correctness | PARTIAL (logic only) | cache task 15/15 on Node type-stripping; no typecheck, no React | isolation + dependency-install policy |
| 3 | Debugging & regression prevention | PARTIAL | pricing task 9/9; regression-test requirement never measured | isolation |
| 4 | Independent code review | PARTIAL | 11/11 keyword recall (lenient); **D13 verified: "reviewer differs" is NOT enforced** (`reviewer-enforcement-gap.md`) | held-out seeded set; enforcement patch (D13b) |
| 5 | Accessibility & responsive | PARTIAL | independent checker at 3 widths on 5 pages (all pass; ceiling) | keyboard/AT walk; more viewports |
| 6 | Animation quality & reduced motion | NOT RUN | review of planted motion defects only (12/12 by keyword) | isolation; browser trace harness |
| 7 | Explicit deterministic skill selection | PARTIAL | **P1 applied**; 20 offline tests pass on the real tree; `ui_design` fails closed until P2; natural-prompt test: 0 of 4 selected | P2 approval; live dispatch check |
| 8 | Security, provenance, isolation | PARTIAL (+ open finding: P1b) | provenance verified on the real tree; **L1 isolation (fs/net/env, node+npm) proven by 13 canaries**; browser-in-sandbox BLOCKED; model-run isolation (L2) unverified | D14 canary run; browser path |

## 1. UI/UX design quality

Objective: Taste direction produces designs that are (a) not the model's default look, (b) high quality, (c) brand-faithful when a brief demands it.
Fixtures (to build): three briefs in different domains with real content inventories (e.g. a clinic booking page, a developer-tool landing page, an internal analytics dashboard app screen), plus one brief with a **strict brand guide** that conflicts with Taste house style.
Procedure: arms = unskilled baseline, Taste (explicit), and optionally each alternate; ≥3 generations per arm per brief; all inside the isolation boundary; outputs rated blind (order randomised, arm hidden) by ≥2 raters on a fixed rubric (distinctiveness, hierarchy, typography, imagery, responsiveness) plus deterministic checks.
Pass: Taste median rubric score exceeds baseline by a pre-declared margin on ≥2 of 3 briefs with inter-rater agreement reported; for every Taste run `.taste-skill/` shows `draw.mjs` ran **and** `DESIGN_DIRECTION.md` names the dealt direction; `inspect.mjs` exit 0 or each FAIL waived with a brief-based reason; the brand-guide brief output follows the guide (brief wins).
Evidence now: one run per arm, one rater (me), directional only. **Erratum:** that Taste arm ran only `inspect.mjs` and never `draw.mjs` or any `references/`/`library/` file, so the "researched directions" mechanism is untested. Status PARTIAL.

## 2. TypeScript/React correctness

Fixture (to build): a React 19 + TypeScript `strict` app with a lockfile — a data table with server-state fetching (stale/race handling), a validated multi-step form, and an optimistic update with rollback — ~15 files, vitest + React Testing Library, ESLint, `tsc --noEmit`, production build; hidden behavioural tests and a hidden accessibility test.
Procedure: dependencies from the lockfile via `npm ci --ignore-scripts` inside the isolation boundary; arms: baseline vs baseline + Ponytail vs baseline + each shortlisted React/TS skill (see complementary capabilities) with a task that triggers the failure class that skill claims to prevent.
Pass: hidden tests 100 %; `tsc` 0 errors; ESLint 0 errors; build succeeds; no new `any` / unchecked `as` beyond a declared budget; React-specific hidden checks (no waterfall: requests issued in parallel; no state mutation; stable keys) all green.
Evidence now: cache task 15/15 for every arm **including baseline** (ceiling) under Node type stripping only: no type check, no JSX, no rendering. Status PARTIAL (logic only).

## 3. Debugging and regression prevention

Fixture (to build): a multi-module repo with three seeded defects of different kinds (an ordering/concurrency bug, a boundary/rounding bug, a state-leak bug) of which only one has a failing visible test, plus a "fix that passes visible tests but regresses behaviour" trap.
Pass: all hidden tests pass; **added regression tests fail when the fix is reverted** (mutation check run by the harness); no edits under `test/` that weaken assertions; diff size reported.
Evidence now: pricing task 9/9 for all five arms; regression-test addition and revert-mutation were never measured. Status PARTIAL.

## 4. Independent code review

Fixture (to build): a held-out set of ≥20 planted defects across 3 files (TS, React, CSS) written by someone other than the reviewer prompt author, plus ≥5 clean-code decoys to measure false positives.
Procedure: author = worker A, reviewer = a *different* worker/harness in a fresh context, read-only profile, inputs limited to diff + evidence report + brief.
Pass: defect recall ≥ 90 % with each finding verified by a human against the plant list (not keyword matching); false-positive rate ≤ pre-declared bound on decoys; reviewer ≠ author enforced by the harness.
Evidence now: 11/11 on one fixture with generous regexes (the baseline matched everything), review by the same family of context. Whether `dispatch` enforces "reviewer differs" is **unverified** (`routing.roles.reviewer` says "prefer"; the `coding` class says "must"). Status PARTIAL.

## 5. Accessibility and responsive behaviour

Procedure: `check_ui.mjs`-class automated checks at 360/390/768/1024/1440/1600 px; Playwright keyboard walk (every interactive element reachable by Tab in a sensible order, visible focus, Esc closes dialogs, no traps); accessibility-tree snapshot names/roles; 200 % zoom reflow; `prefers-reduced-motion` and forced-colors smoke.
Pass: zero failures on all of the above across the fixtures of gates 1 and 2; any exception explicitly waived in the report.
Evidence now: automated checker at three widths on five pages: all pass, including the unskilled baseline (ceiling). No keyboard walk, no assistive-technology check, no real devices. Status PARTIAL.

## 6. Animation quality and reduced motion

Fixture (to build): the Gate 1/2 pages with specified motion (modal entrance, list reorder, hover, a scroll scene).
Pass (deterministic where possible): no animation of layout properties (`width/height/top/left/margin`) except declared; no `transition: all`; with `emulate_media reducedMotion=reduce`, `document.getAnimations()` holds no non-essential running animations; no frame over a declared long-frame threshold in a Chrome trace on a 4× CPU throttle; durations within declared bounds; every motion has a stated purpose in `DESIGN_DIRECTION.md`.
Evidence now: only a regex for the string `prefers-reduced-motion` in generated pages (present in all five) and a review-of-planted-defects test (12/12 by keyword, baseline included). Motion *implementation* quality has not been measured. Status NOT RUN. `review-animations` is user-invocation-only and failed headless, so it cannot be a worker gate.

## 7. Explicit, deterministic skill selection

Procedure/pass: (a) offline: the same `task_type` yields an identical plan across repeated runs; non-UI task types never select a design skill; tampered or re-augmented vendored tree ⇒ `integration-undeliverable`; delivery failure after planning ⇒ `blocked` with no worker call; skill copy and working files never committed; HOME untouched; (b) live: a dispatched Claude worker for `ui_design` has the skill in its worktree and the instruction in its prompt, a `coding` worker has neither, and the skill's script artifacts appear.
Evidence now: (a) **20 tests pass on the real tree after P1** (`evals/test_wave_c1_production.py`), mutation-checked (no cleanup ⇒ 3 fail; `deliverable` always true ⇒ 2 fail; writing the shared git exclude ⇒ 1 fails); full real-tree regression 1051 passed, 3 skipped. Taste is still inert: `ui_design` plans `blocked`, `coding` unchanged. (b) not run. The natural-prompt test (0 of 4 selected) is the evidence that explicit routing is required. Status PARTIAL.

## 8. Security, provenance and execution isolation

Procedure/pass: vendored files re-hash to the lock; the upstream pin reproduces from a fresh clone; no `hooks/`, no `assets.mjs`, no `skills/design-taste-frontend`; no write to `~/.claude`, `~/.codex`, OpenCode, Hermes or `skills/`; every executing gate runs inside the isolation boundary above; no credential reachable from the boundary.
Evidence now (real tree): fresh clone of tag `v2.1.5` reproduced commit `12af471f627f866411b4bd785b19646d3672784c` and the identical 36-file SHA-256 manifest and LICENSE hash; `scripts/verify_skills_lock.py` reports OK; `scripts/runtime/test_skills_lock.py` 9 passed including negative tests (tampering, reintroduced downloader, unlisted file, hooks, premature activation, missing licence); protected manifest still matches; home directory not written. **Added 2026-10-25:** `isolation/canary.sh` runs 13 canaries against a deny-default Seatbelt profile (writes only inside the work dir; outside reads/writes, loopback network and inherited environment denied; node and offline npm run inside) — all PASS, host-verified. **Not met:** Chrome cannot run inside the profile without write access to the real browser profile (BLOCKED, not worked around); isolation of a *model run* (Claude Code native sandbox) is documentation-only and unverified (D14). No gate that runs a model under skill scripts may be claimed. Status PARTIAL.
