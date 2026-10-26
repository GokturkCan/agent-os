# Wave C1 — engineering, UI/UX and agent skills (review, benchmark, preparation)

Status: review done; **D1 applied** (Taste Skill staged dormant, hash-verified); production pipeline specified in `docs/wave-c1-production-pipeline.md`; the protected packet is prepared and **unapplied** (`audit/wave-c1/protected-packet/`); acceptance gates in `audit/wave-c1/acceptance-matrix.md` (none PASS yet); scoped capability shortlist in `audit/wave-c1/complementary-capabilities.md`. **P1 is applied** (inert; Taste remains dormant; `ui_design` fails closed). Isolation proposal, dependency policy and reviewer-enforcement gap: `audit/wave-c1/{isolation-harness-proposal,dependency-policy,reviewer-enforcement-gap}.md`. Nothing is activated, committed, pushed or merged. Branch `feature/wave-c1-engineering-ui` from `main` 56a1c6e. Architecture unchanged: Hermes is the sole orchestrator, Agent OS the capability/policy/evaluation platform, SecondBrain the sole memory.

Detailed evidence lives in `audit/wave-c1/`: `capability-matrix.md` (every candidate and module, with lifecycle state and decision), `benchmark-results.md` (25 valid runs, limitations, NOT TESTED list), `installation-packet.md` (the approval packet), `bench/` (reproducible harness).

## Baseline (Phase 0)

`main` == `origin/main` == 56a1c6e (PR #8 merge); tree clean; protected manifest matched; config valid; 1022 passed / 3 skipped (evals + wrapper tests); `feature/run4-research-plane` untouched at a2c0897; no global Claude/Codex/OpenCode/Hermes setting changed.

## Verdict

| Decision | Candidates |
|---|---|
| **ADOPT** (dormant, optional specialist, explicit dispatch only) | Taste Skill v2.1.5 `design-taste-frontend` (subset, `assets.mjs` excluded) |
| KEEP EXISTING | Superpowers (process SOP), Ponytail (simplicity; pinned v5.3.2), OpenSpec (dormant), anthropics/skills + claude-plugins-official (existing sources), Karpathy guidelines (covered), Matt Pocock and Addy skills (no lift) |
| DEFER | Anthropic frontend-design, ui-ux-pro-max, Emil Kowalski skills, Vercel react/composition/view-transitions skills, pinned Web Interface Guidelines, taste-skill-classics, DESIGN.md + Stitch skills, Spec Kit, individual ECC / wshobson skills |
| REJECT | gstack, ECC and wshobson as packs, ComposioHQ, planning-with-files, Vercel `web-design-guidelines` as shipped (mutable remote rules), `vercel-optimize`, `deploy-to-vercel`, `vercel-cli-with-tokens` |
| NOT TESTED | Refero Styles, 21st.dev Magic, Motion+ AI Kit, imagegen-skills (paid/keyed); task 4 (spec → impl → review); Codex/OpenCode/Hermes/Antigravity loading |

## What the evidence says (and does not)

- Bounded engineering tasks (implementation, review, debugging) and an accessibility-constrained UI redesign all **hit the ceiling without any skill**: hidden-test pass rates were identical across arms (15/15, 9/9), review recall 11/11, every redesign passed every automated WCAG-style check. Skills only added cost (+13 % to +116 %).
- The one differentiator was visual identity: baseline, frontend-design and ui-ux-pro-max converged on the same navy/cream/serif/amber layout; Taste Skill produced a distinct, responsive design at ≈2× latency (n = 1, single rater).
- **Installed ≠ discoverable-and-used:** four UI skills installed together were never selected on a natural prompt. Selection must be explicit.
- Many candidate skills are human-slash-only (`disable-model-invocation`): 23/38 Matt Pocock, 7/7 Taste Classics, 3 Emil skills including `review-animations`, which failed headless. They are not worker-eligible.
- Upstream drift found: Taste Skill moved 2.1.4 → 2.1.5; Ponytail upstream is ahead of the reviewed v5.3.2; Karpathy skill now declares MIT in frontmatter; Superpowers upstream is 7.0.1 (installed 7.0.0).
- Security finding: Vercel's `web-design-guidelines` fetches its rules from a mutable `main` URL at review time.
- **Erratum:** the Taste benchmark arm never ran `draw.mjs` or read `references/`/`library/` (see `benchmark-results.md`); its measured effect came from `SKILL.md` prose plus the inspector loop.
- Limits: n = 1 per arm, one model, synthetic fixtures, lenient keyword recall for review tasks. No claim of statistical significance.

## Approval needed

See `audit/wave-c1/installation-packet.md` §7 (D1–D9). The minimum useful approval is **D1** (stage dormant under `third_party/` with lock and docs). Registry/test/manifest changes are protected and need their own packet (D2).

## Follow-on backlog (not started; nothing from these tracks was installed)

| Track | Scope | Entry condition |
|---|---|---|
| C2 Scientific Skills | scientific skill registry, Orchestra overlap review | Run 4 plan settled; UNVERIFIED sources need URLs |
| D Context/Token Efficiency | RTK, Headroom, ContextGate | measured token budget per worker; hook-free options only |
| E Visual Code Intelligence | Graft/Trail-Code, Archify, Codegraph, Graphify | a large real repo exists; compare against Serena first |
| F Web Research | Crawl4AI, Firecrawl, Crawlee, Scrapy, Scrapling, browser-use | network/credential policy; Playwright MCP is the baseline |
| Run 4 Research Plane + knowledge gate | `feature/run4-research-plane` | separate authorisation; branch preserved |
| Compute plane | Mac mini ↔ MSI, local model plane | compute contract (`docs/compute-contract.md`) |
| Hermes Agent Factory | WhatsApp / Telegram / OpenMuse interfaces | Hermes remains sole orchestrator; credential design first |
| Production | self-hosted production, sandbox, observability, recovery | hard sandbox (deny patterns are not one) |
| Wave C1 follow-ups | n ≥ 3 blind-rated UI repeats, task 4 pipeline, harder TS/React tasks, host acceptance in scratch dirs, Superpowers 7.0.1 patch | D6/D8 |
