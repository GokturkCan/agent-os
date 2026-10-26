# Wave C1 — complementary capabilities (scoped recommendations; nothing bulk-installed)

Decision rule for this document (owner instruction): a candidate is not rejected because one easy benchmark showed no advantage. Each entry states **the production failure it would prevent**, whether that has been **demonstrated** (almost none have: the Wave C1 tasks saturated), and the **acceptance test** that would demonstrate it. Where the earlier matrix said DEFER/KEEP EXISTING, that was *no demonstrated lift on bounded tasks*, not a verdict on the failure class.
Hard blockers remain blockers: security findings and architecture conflicts (below) are not overridden by "no benchmark yet".

## A. Already available — reuse, no new install

| Capability | Unique production failure it prevents | Pipeline stage | Status |
|---|---|---|---|
| Claude Code / Codex workers (coder, reviewer profiles) | no isolated, budgeted execution | 6, 10 | adopted; Codex excluded from `ui_design` until skill delivery verified |
| Ponytail (pinned v5.3.2, 2 skills) | over-engineered diffs, speculative abstraction (measured: −40 % code on the cache task) | 6 | adopted; explicit on request; `ponytail-review` missed 2/11 planted defects, so it does not replace an independent review |
| Serena | edits to the wrong symbol, missed references on rename | 6 | adopted (`exposure.coder`) |
| Context7 | stale or hallucinated library API usage | 6 | adopted (`exposure.coder`) |
| Playwright MCP (per task via the plan) | unverified visual/behavioural claims ("looks fine") | 7, 8 | adopted; selected by `ui.visual_qa` for `ui_design` |
| Agent OS verifier, budgets, policy, evals, telemetry | un-evidenced "done", runaway loops, unreviewed protected edits | 9, 11, 12 | adopted |

## B. Scoped adoption recommendations (modules, not packs)

None is staged by this pass. Staging any of them is a separate D1-style decision using the same pattern as Taste (pin, hash lock, dormant under `third_party/`, task-scoped delivery, registry record under approval).

| Candidate / exact modules | Unique production failure it prevents | Demonstrated here? | Acceptance test that would show it | Constraints and risks | Recommendation |
|---|---|---|---|---|---|
| **Vercel `react-best-practices`** (7.3 KB SKILL + 4 refs + rules; 416 KB folder) and **`composition-patterns`** (2.9 KB + rules; 80 KB) — `vercel-labs/agent-skills` @ `063bee9` | request waterfalls, bundle bloat, needless re-renders, boolean-prop proliferation: failures that **pass unit tests** | No. Review of a seeded component: baseline 11/11 = skill 11/11 (+116 % cost). That test did not target performance failures | gate 2 fixture containing a waterfall and a heavy import: tests green, but a Playwright network trace shows serial requests and a bundle-size budget fails; skill arm must fix both without breaking tests | model-invocable; no scripts; no root LICENSE (skill-level MIT); large rules folder (read on demand) | **Candidate for gate 2** (React tasks only). Exclude `vercel-optimize` (90 scripts), `deploy-to-vercel`, `vercel-cli-with-tokens` (tokens), and `web-design-guidelines` as shipped (mutable remote rules). `react-view-transitions` only if a project uses the API |
| **Matt Pocock `codebase-design`** (6.4 KB, 3 refs, model-invocable) and **`migrate-to-shoehorn`** (2.8 KB) — `mattpocock/skills` @ `5beb35b` | shallow modules / leaky interfaces; unsafe `as` casts in tests hiding type errors | No | gate 3 / gate 2 fixture: a module whose interface leaks internals; reviewer rubric for depth; test fixture with `as any` casts migrated without behaviour change and with `tsc` still clean | `setup-ts-deep-modules` is **user-invocation-only** (not worker-eligible) and wires `dependency-cruiser` (a dependency install); `migrate-to-shoehorn` needs a package install; 23/38 skills in the repo are user-only; `tdd`/`diagnosing-bugs` duplicate Superpowers | **Candidate for `codebase-design` only**; `migrate-to-shoehorn` conditional on the install policy; skip the rest |
| **Emil Kowalski `animation-performance`** (14 KB, no scripts) and **`break-ui`** (14 KB, 1 ref) — `emilkowalski/skill` @ `2d22863` | janky or layout-thrashing animation, missing reduced-motion handling; UI that breaks on worst-case data (very long names, unbreakable strings, empty/huge lists) | No. Animation review of planted defects: baseline 12/12 = skill 12/12 (+59 % cost). Implementation quality never measured | gate 6 fixture: specified motion implemented, then `getAnimations()` under reduced motion, long-frame trace under CPU throttle, layout-property check; `break-ui`: gate 5 fixture fed worst-case data, no overflow/clipping, no console errors | both model-invocable. `review-animations`, `prototype`, `pick-ui-library` are user-invocation-only and `review-animations` failed headless. `emil-design-eng` is 27 KB (heavy) | **Candidate for gate 6 / gate 5**: `animation-performance` and `break-ui` only |
| **Anthropic `frontend-design`** (9.4 KB, Apache-2.0, no scripts, identical to the official plugin copy) | the generic "AI-template" look (it names the clichés) | Partly: its output converged on the same default look as the unskilled baseline in one run, at −21 % cost | gate 1 protocol as an arm | tiny, trusted source; overlaps Taste's purpose | **Optional alternate design specialist** (registered `future` in the packet); explicit human choice only, never an automatic fallback |
| **UI UX Pro Max** (`nextlevelbuilder/ui-ux-pro-max-skill` @ `d14efff`; uupm.cc is the project landing page) | inconsistent design systems across screens (it generates a searchable style/palette/type database and a design-system file) | No; in one run the model never executed its search script and the output matched the baseline cluster | gate 1 protocol as an arm; verify the database actually gets queried | 3.6 MB, python scripts, an npm CLI installer that writes into agent dirs (do not use the installer), network use in some helpers | **Optional alternate**, vendored per task only if ever chosen; never use `uipro` |

## C. Not adopted — blockers that stand regardless of benchmarks

| Candidate | Blocker |
|---|---|
| gstack | bundles `setup-gbrain` (a second memory system, violates SecondBrain-only) and `setup-browser-cookies` (imports real browser cookies); hooks and installers; 30–137 KB skills |
| ECC (1062 skills), wshobson, ComposioHQ | competing harness / persona sprawl / third-party OAuth gateway; individual UI skills may be re-audited one by one later |
| planning-with-files | per-prompt and per-tool hooks (permanent context injection) |
| Vercel `web-design-guidelines` **as shipped** | fetches rules from a mutable URL at run time (unpinned remote instructions). A pinned local copy (`vercel-labs/web-interface-guidelines` @ `434b7f9`, MIT) is acceptable as data, not adopted yet |
| Refero Styles, 21st.dev Magic, Motion+ AI Kit, imagegen-skills | paid subscription, API key/token or hosted service; not tested; owner has not authorised credentials |
| Spec Kit | needs `uv tool install` (a new tool); OpenSpec already covers the class and stays dormant |

## D. How the shortlist maps to the gates

Taste → gates 1, 5 (inspector). Vercel React + composition → gate 2. Matt Pocock `codebase-design` → gates 2, 3, 4 (review rubric). Emil `animation-performance` + `break-ui` → gates 6, 5. Anthropic `frontend-design` / UI UX Pro Max → gate 1 as comparison arms only. Every one of these entries stays **unstaged** until the isolation harness exists and its gate has a defined fixture, because their value claim is precisely the thing no existing evidence supports or refutes.
