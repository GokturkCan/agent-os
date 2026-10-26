# Wave C1 — benchmark evidence and limitations

2026-10-25 · model `claude-sonnet-5-5` for every arm · harness and raw material in `audit/wave-c1/bench/` (fixtures, hidden tests, prompts, scripts, checker output, final texts, the five generated UI pages).

## Method

- Every arm ran as a fresh `claude -p` in its own scratch git repo with `--setting-sources project --strict-mcp-config --no-session-persistence`. A probe confirmed the run saw **no user skills, no hooks, no plugins, no MCP servers** (only Claude Code's built-in skills); fixed overhead ≈ 11.7 k tokens.
- A candidate skill was copied into that repo's own `.claude/skills/` (project scope). Nothing was written to `~/.claude`, `~/.codex`, OpenCode, Hermes, or `~/agent-stack/skills`.
- Arms were told "Use the `<skill>` skill" (explicit invocation) so skill *quality* is isolated from trigger rate; the **trigger rate was tested separately** (natural arm).
- Denied for every arm: WebFetch/WebSearch, curl/wget, npm/npx/pip, gh, security, sudo, open, and `assets.mjs` (network downloader). Allowed: node, python3, git and read-only shell utilities. No dependency was installed; TypeScript ran on Node 24's built-in type stripping.
- "Used" is read from the stream log (`Skill` tool_use), never assumed.
- Hidden tests and planted-defect lists lived outside the workspace. **Each hidden suite was first validated against a reference solution** (debug 9/9, cache 15/15) and against the buggy start (debug failed 4/9). Two fixtures were corrected after validation (an under-specified spec clause and a mis-written test); both fixes preceded every scored run.
- UI scoring used an independent checker written for this benchmark (`bench/tools/check_ui.mjs`: headless Chrome over CDP at 390/768/1440; overflow, WCAG contrast, tap targets, fake buttons, alt, labels, focus indicators, landmarks, content preservation, self-containment). It scrolls the page first so scroll-reveal content is measured; an earlier version did not, and a blank-looking screenshot of the taste output was a checker artefact, since fixed and re-measured.

## Results

### Run log (all 25 valid runs)

| run | cost $ | turns | wall s | out tok | new input tok | Skill tool called |
|---|---|---|---|---|---|---|
| impl__base | 0.118 | 8 | 41 | 5692 | 13228 | - |
| impl__pt (ponytail) | 0.109 | 9 | 35 | 4749 | 13485 | ponytail |
| impl__mp_tdd | 0.129 | 12 | 44 | 5600 | 15078 | tdd |
| impl__ao_tdd | 0.193 | 14 | 58 | 8557 | 22944 | test-driven-development |
| impl__sp_tdd | 0.197 | 14 | 63 | 9492 | 21983 | test-driven-development |
| debug__base | 0.062 | 6 | 20 | 1816 | 9488 | - |
| debug__ao | 0.070 | 6 | 15 | 1505 | 12681 | debugging-and-error-recovery |
| debug__mp | 0.085 | 7 | 20 | 2165 | 13703 | diagnosing-bugs |
| debug__pt | 0.076 | 7 | 20 | 2247 | 11804 | ponytail |
| debug__sp | 0.076 | 8 | 19 | 1640 | 12867 | systematic-debugging |
| review__base | 0.050 | 2 | 18 | 1850 | 7327 | - |
| review__mp | 0.064 | 5 | 21 | 2075 | 9474 | code-review |
| review__pt | 0.070 | 5 | 26 | 2762 | 9162 | ponytail-review |
| review__ao | 0.085 | 5 | 23 | 2228 | 14609 | code-review-and-quality |
| review__vercel | 0.108 | 5 | 24 | 2207 | 20257 | vercel-react-best-practices |
| ui__base | 0.236 | 4 | 81 | 14191 | 21959 | - |
| ui__fd (frontend-design) | 0.186 | 5 | 64 | 9907 | 20584 | frontend-design |
| ui__uupm (ui-ux-pro-max) | 0.172 | 5 | 58 | 8401 | 20767 | ui-ux-pro-max |
| ui__taste (design-taste-frontend) | 0.319 | 14 | 163 | 13149 | 39165 | design-taste-frontend |
| ui__natural (4 UI skills installed, no instruction) | 0.137 | 3 | 52 | 7600 | 14188 | **none** |
| audit__base | 0.064 | 2 | 25 | 3028 | 7907 | - |
| audit__wdg (pinned guidelines) | 0.077 | 4 | 28 | 3504 | 9738 | web-design-guidelines-pinned |
| anim__base | 0.061 | 5 | 24 | 2587 | 7422 | - |
| anim__ap (animation-performance) | 0.097 | 4 | 19 | 2072 | 18561 | animation-performance |
| anim__ra (review-animations) | 0.029 | 2 | 6 | 220 | 5991 | review-animations — **tool refused: user-invocation-only; no review produced** |

Runs invalidated and re-run, not counted: ui__uupm and ui__natural (first attempt: skill install silently failed on a zsh `:u` parameter-modifier bug in my launcher), audit__wdg (same class of bug, `:w`). Originals kept in the scratch `invalid/` folder.

### T1 — TypeScript implementation (TTL-LRU cache, 15 hidden tests)

| arm | hidden pass | LOC | cost | note |
|---|---|---|---|---|
| baseline | 15/15 | 138 | $0.118 | |
| Ponytail | 15/15 | **83** | $0.109 | smallest |
| Matt Pocock `tdd` | 15/15 | 97 | $0.129 | |
| Addy `test-driven-development` | 15/15 | 123 | $0.193 | +64 % |
| Superpowers TDD | 15/15 | 110 | $0.197 | +67 % |

**Ceiling effect: correctness does not discriminate.** Differences are cost, size, latency.

### T1b — React review (11 planted defects, keyword recall — lenient instrument)

baseline 11/11 · vercel react-best-practices 11/11 (+116 % cost) · Addy 11/11 (+70 %) · Matt Pocock 11/11 (+28 %) · **ponytail-review 9/11** (missed stale closure and unsafe `as User[]` cast; 1045 words vs 677). Spot-verified: the two misses are real, the matches are on topic. Recall regexes are generous, so 11/11 means "mentioned", not "perfectly explained". Precision / false positives were not scored.

### T5 — Debug and simplify (3 seeded bugs, only one visible)

All five arms reached **9/9 hidden tests**. Baseline finished in 20 s for $0.062; skill arms cost +13 % to +37 %. Baseline output: 85 → 30 lines. No process skill found the two non-visible bugs faster or more reliably; the baseline already did. LOC of the skill arms was not collected (hidden tests only), so there is no simplification comparison for this task.

### T2 — UI redesign with responsive + accessibility requirements

Legacy page: 830/452/0 px overflow at 390/768/1440, 30 of 34 text elements fail contrast (worst 1.92), 12 fake buttons, 3 images without alt, unlabeled input, no landmarks/lang/viewport.
**All five redesigns passed every automated check** (0 overflow, 0 contrast failures, worst ratio 6.15–7.72, 0 fake buttons, alt/labels/focus/landmarks present, all content kept, no external requests): another ceiling effect.

Visual outcome (single rater, me, n = 1 per arm; screenshots in the scratch run folder, generated HTML in `bench/outputs/`): baseline, frontend-design and ui-ux-pro-max **converged on the same navy + cream + serif + amber card layout** — the "AI default cluster" that Anthropic's own frontend-design text describes. `design-taste-frontend` was the only arm that produced a different identity (dark teal, grotesque sans, orange field, interactive history slider tied to the plans, giant wordmark footer) and it held up at 390 px. Cost: **+35 % dollars, 2× wall time, +78 % input tokens vs baseline**, because it runs its draw/inspect loop (14 turns).
Caveats: one sample per arm, no blind jurors, no repeat run; variance between runs of the same arm is unmeasured. This is directional evidence, not proof.

### Skill-trigger test (INSTALLED/DISCOVERABLE vs ACTUALLY USED)

With frontend-design, design-taste-frontend, ui-ux-pro-max and emil-design-eng installed together and a natural prompt, **0 Skill calls**. Dispatch to a UI skill must be explicit (task template / router rule), not left to description matching.

### T3 — Browser-screenshot visual QA

- The taste inspector (`inspect.mjs`, run on three pages after code review) agreed with the independent checker on the legacy page (overflow, contrast, small text, missing title) and exits non-zero on FAIL. Findings: legacy 16 FAIL / 4 WARN; baseline redesign 6 FAIL / 5 WARN; taste redesign 1 FAIL / 3 WARN.
- **Circularity warning:** most inspector rules are the skill's own house style (eyebrow labels, icon cards, shadows, hairlines, cream palette). The taste output passing them is expected by construction. It does *not* test labels, alt text, focus visibility or fake buttons — those came from my checker.
- Playwright MCP (already adopted) provides screenshots; the inspector's incremental value is a repeatable rule bundle, not browser access.
- **NOT TESTED:** a full LLM look-and-fix loop comparing a screenshot-driven baseline with the inspector loop (only the taste arm's own built-in loop ran inside T2).

### Animation review (12 planted motion defects, keyword recall)

baseline 12/12 · animation-performance 12/12 (+59 % cost) · review-animations **not runnable** (user-invocation-only, mandatory canned first reply). No evidence of lift.

### Pinned Web Interface Guidelines (12 planted a11y/responsive defects)

baseline 12/12 · pinned guidelines 12/12 (+20 % cost). The upstream skill's runtime fetch from a mutable `main` URL was not exercised (WebFetch denied) and is rejected on security grounds.

## NOT TESTED (and why)

| Item | Reason |
|---|---|
| Task 4: spec → implementation → independent review | needs multi-session independent reviewers and (for Spec Kit) a `uv tool install`; only static comparison |
| Spec Kit `specify` CLI | installing it is forbidden in this pass |
| Refero Styles, 21st.dev Magic, Motion+ AI Kit, imagegen-skills, Stitch-based skills | require paid accounts, API keys/tokens or hosted services; the owner has not authorised credentials |
| Codex, OpenCode, Hermes, Antigravity loading of any new skill | no host config may change in this pass; format inference only. Antigravity UNVERIFIED |
| Reproducibility / variance | n = 1 per arm, no repeats |
| `taste-skill assets.mjs` | network downloader, denied in the harness; not part of the proposed install |
| Harder engineering tasks (multi-file refactors, concurrency, real React rendering) | would need npm installs; the chosen tasks saturated |
| Real React rendering/type-checking | `tsc`, React not installed; TS ran via type stripping |

## Erratum (2026-10-25, found while preparing the implementation pass)

Re-reading the Taste arm's stream log: the model **never ran `draw.mjs`** (no direction was dealt) and **never read any `references/*.md` or `library/*.json` file**; it ran only `inspect.mjs`, repeatedly, and read the generated report. The measured visual divergence therefore came from `SKILL.md` prose plus the inspector loop, **not** from the dealt-directions library that the skill advertises. Statements above and in the matrix that describe Taste as "dealing researched directions" describe the skill's design, not what this run exercised. Consequences: the 2.3 MB library is unproven value; acceptance gate 1 now requires evidence that `draw.mjs` actually ran; whether a prose-only subset would have sufficed is an open question, not tested. The results table itself is unchanged.

## What this evidence supports

1. On bounded, well-specified engineering tasks the current model without any skill already reaches the ceiling; process skills add **+13 % to +116 % cost** with no measured correctness gain. No engineering pack should become a default.
2. The only measured differentiator is **art direction** (taste-skill), and only on visual outcome, at roughly double the latency.
3. Selection is not automatic. Any adopted skill needs explicit routing.
4. Many candidates are human-slash-only (`disable-model-invocation`) and are therefore not worker-eligible at all.
5. Absolute claims stop there: n = 1, one model, one rater, synthetic fixtures.
