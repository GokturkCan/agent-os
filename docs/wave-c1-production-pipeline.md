# Wave C1 — taste-first production engineering pipeline (specification)

Status: **specification.** D1 (Taste Skill staged dormant) and **P1** (inert protected integration) are applied; **P2 (activation) is not**. Items marked **[P1]** are now in the tree but inert (`ui_design` fails closed); **[P2]** items are in the unapplied packet (`audit/wave-c1/protected-packet/`).
Owner decision (2026-10-25): Taste Skill is the primary UI/UX design direction for frontend work. Hermes is the sole orchestrator, Agent OS provides capability selection, policy, execution and verification, SecondBrain is the sole durable memory. No second orchestrator, no second skill router, no new memory.

## 1. Design principle

Reuse the machinery that already exists: `agentos intent` → router task classes → `capability_policy.plan_for` (registry data) → `dispatch` (task contract, worktree, worker launch, verifier, budgets, telemetry). The only genuinely missing piece is **delivering one skill to one dispatched worker, verified, for one task**. Everything else is registry data and a task class.

Why task-scoped delivery rather than copying the skill into `skills/` (the Hermes loading path) or `~/.claude`: nothing global changes; interactive Claude/Codex/OpenCode and Hermes never see the skill; the skill is present only in the worktree of a task whose type selected it; rollback is deleting one registry line. (This supersedes `installation-packet.md` §4c.)

## 2. Flow

```
Hermes request
  1 intake        agentos intent               existing: preloads agent-os-orchestrate for mutation requests
  2 classify      Hermes chooses task_type     ui_design | coding | review      [P1: ui_design class]
  3 select        capability_policy.plan_for   registry data, no LLM            [P1: task_types/preferences]
  4 brief         worker, DESIGN_BRIEF.md      deterministic acceptance
  5 direction     Taste: draw.mjs -> DESIGN_DIRECTION.md      skill delivered per task [P1: skill_delivery]
  6 implement     TypeScript/React in the task worktree
  7 visual QA     Playwright MCP + Taste inspect.mjs   screenshots 390/768/1440
  8 a11y          deterministic checker + keyboard walk (Playwright)
  9 verify        project `verify` command: typecheck + lint + test + build (+ QA gates), exit 0
 10 review        separate dispatch, task_type review, worker != primary
 11 repair        existing budgets: same task_id retried until success / no_progress / budget
 12 evidence      final report from telemetry + task state + artifacts (draft to SecondBrain inbox only)
```

## 3. Stages: mechanism, artifact, exit criterion

| # | Stage | Existing component | New in packet | Artifact (in worktree unless stated) | Exit criterion / failure handling |
|---|---|---|---|---|---|
| 1 | Intake | `agentos/intent.py`, `config/routing.yaml intent_rules` | — | intent decision in telemetry | non-mutation requests are not forced (unchanged) |
| 2 | Classification | `routing.task_classes`; Hermes via `agent-os-orchestrate` | `ui_design` task class [P1] | `task_type` in the task contract | **Honest limit:** choosing `ui_design` vs `coding` is Hermes' (model) decision. Determinism starts at `task_type`. A mis-typed task simply gets no art-direction skill; it never gets the wrong one. An intent rule for UI wording is deliberately not proposed (false positives would change routing). |
| 3 | Selection | `capability_policy.plan_for`, `registry.policy.task_types/capability_preferences`, executor `integrations`, deliverability predicate | `ui_design → [ui.art_direction, ui.visual_qa, code.edit, code.test]`; preference `ui.art_direction: [taste-skill, frontend-design, ui-ux-pro-max]`; `skill_delivery.deliverable` [P1] | plan in telemetry (`capabilities`) | blocked plan ⇒ `human_handoff`-style stop, never a silent skill-less run |
| 4 | Design brief | dispatch `prompt`, task contract acceptance | prompt template (this doc §6) | `DESIGN_BRIEF.md`: audience, primary job, content inventory (verbatim facts), constraints (brand, viewports 360–1600, a11y level, performance budget), non-goals | `verify` fails if file/headings missing |
| 5 | Taste direction | — | `agentos/skill_delivery.py` [P1] provisions `<wt>/.claude/skills/design-taste-frontend` after hash verification; explicit instruction line prepended to the prompt | `DESIGN_DIRECTION.md` naming the dealt direction; `.taste-skill/` working files (git-excluded) | evidence = files left by the skill's scripts (deterministic). **Erratum:** in the Wave C1 benchmark the model never ran `draw.mjs` or read `references/`/`library/`; gate 1 requires that this step actually runs |
| 6 | Implementation | claude_code `coder` profile; Serena, Context7 (exposure.coder); Ponytail on request | — | commits on `agentos/<task_id>` | worker returncode + verifier |
| 7 | Browser visual QA | Playwright MCP (added per task by the plan via `extra_mcp`), `mcp_playwright` grant on `coder` | taste `inspect.mjs` ships with the delivered skill | screenshots + `inspect/report.json` | FAIL findings must be fixed or explicitly waived in the report |
| 8 | Accessibility | — | promote `audit/wave-c1/bench/tools/check_ui.mjs` (independent checker) to a verifier script (**not in P1**, see §7) | checker JSON per viewport | 0 failures at all viewports; keyboard walk passes |
| 9 | test/typecheck/lint/build | `dispatch(verify=...)`, `_verify` | project-defined `npm run verify` | verify summary in task state | exit 0 required; failed verify = one consumed attempt, task stays open |
| 10 | Independent review | `routing.task_classes.review`, `reviewer` profile (read-only), "reviewer differs" rule | — | structured findings | no unresolved high findings; reviewer must be a different worker than the author (see gate 4 for the enforcement gap) |
| 11 | Repair loop | `taskstate` budgets: `max_attempts 3`, `max_iterations 20`, `no_progress_after 3`, `wall_clock 60 min` | — | iteration history | exits `success` / `no_progress` / `budget_exhausted` / `timeout` / `human_handoff`; reviewer findings become the next attempt's instruction |
| 12 | Evidence report | `telemetry`, task state, `knowledge` gate (drafts only) | `capabilities.skills` and `capabilities.skill_evidence` fields [P1] | `evidence.md` (template §6) | report cites artifacts by path + sha256; nothing canonical is written to SecondBrain `wiki/` |

## 4. When Taste is used (and when it is not)

Use `ui_design` (⇒ Taste) for: new pages, redesigns, visual polish of public-facing sites and app screens (dashboards, settings).
Use plain `coding` (no design skill) for: bug fixes, refactors, API/backend, tests-only, dependency work, copy-only changes.
Alternates (`frontend-design`, `ui-ux-pro-max`) are registered `future` and are **never an automatic fallback**: if Taste is unavailable or fails verification the plan blocks and a human decides. Choosing an alternate is a registry change under approval.
Brand fit: Taste's house style is opinionated (it flags eyebrow labels, cream palettes, icon cards). A brand brief in `DESIGN_BRIEF.md` wins over house style; the report must list any inspector FAIL that was waived because of the brief.

## 5. Selection is deterministic, evidenced, and bounded

- `task_type → capabilities → provider` is registry data; the same inputs give the same plan (tested over repeated plans).
- Description matching is not relied on: the Wave C1 natural-prompt test showed 0 of 4 installed UI skills selected unprompted.
- Delivery is fail closed at two points: planning (`integration-undeliverable` if the vendored tree does not verify) and dispatch (`blocked` if provisioning fails after planning). A selected skill is never skipped silently.
- Codex is excluded from `ui_design` until project-skill loading under `codex exec` is verified (executor integration `unknown`).
- **Open limit:** dispatched Claude workers return `--output-format json`, which does not list `Skill` tool calls. Usage evidence is therefore filesystem evidence (the skill's script artifacts) plus the explicit instruction in the prompt, not a tool-call log. A launch-format change would be a protected `workers.yaml`/`workers.py` change and is **not** in P1.

## 6. Templates

Prompt (generated for `ui_design`): `Use the \`design-taste-frontend\` skill (installed in this project) for the design direction of this task; do not use it for non-UI work.` followed by the brief and the verify command.
`evidence.md` fields: task id and branch; task_type; capability plan (providers, skills, MCP); skill delivery record (name, pin commit, files verified); artifacts (path, bytes, sha256); verify command and result; QA results per viewport; a11y results; review findings and their disposition; repair iterations; waived findings with reasons; limitations and anything NOT RUN.

## 7. What this packet does not solve (kept visible)

0. **Symlink finding (P1b): fixed and applied** under D15: delivery no longer follows worker-planted symlinks, skips FIFOs/devices and caps evidence (9 adversarial tests; 7 failed against the pre-fix module).

1. **Execution isolation.** Dispatched workers have `Bash` inside their profile; deny patterns are command-text matching, not a sandbox. A worker running a third-party skill script can run arbitrary code as the user. Gates that execute skills under a model are therefore **NOT RUN**. Update: a deny-default Seatbelt profile with 13 passing canaries now covers deterministic tool execution (`audit/wave-c1/isolation-harness-proposal.md`); Docker is unavailable (daemon not running), browser-in-sandbox is BLOCKED, and model-run isolation is unverified (D14).
2. **Dependency installation** for real React projects (`npm ci --ignore-scripts` from a lockfile, network policy). Needed by gates 2, 5, 6. Not designed here.
3. **Skill-use telemetry** beyond filesystem evidence (§5).
4. **Codex delivery path** for skills.
5. **A11y verifier promotion** (the independent checker is a benchmark prototype; promoting it is unprotected code but out of scope for this pass).
6. **Reviewer-differs enforcement:** verified NOT enforced (`audit/wave-c1/reviewer-enforcement-gap.md`): `reviewer_rule` strings have no consumer, `roles.reviewer` says "prefer", routing returns `claude_code` for both author and review. Gate 4 needs a separate enforcement patch (D13b).
