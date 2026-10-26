# Wave C1 — protected approval packet

> **STATUS 2026-10-25 (updated): P1 and P1b APPLIED** (P1b under the D15 addendum in `APPROVAL.md`; manifest byte-identical to `P1b-resulting-protected-manifest.json`; real-tree regression 1060 passed, 3 skipped). **P2 remains unapplied.** Original P1 status: **P1 APPLIED** under the recorded approval `audit/wave-c1/APPROVAL.md` (patch hash `f4cb17fa…0943`; manifest refreshed, byte-identical to `P1-resulting-protected-manifest.json`, 79 entries; real-tree regression 1051 passed, 3 skipped). **P2 (activation) is NOT approved and NOT applied**; Taste remains `benchmark`/`dormant`. The text below is the original packet and is kept unchanged.

Prepared 2026-10-25 on `feature/wave-c1-engineering-ui` (base `main` 56a1c6e + approved D1 staging).
**D1 is the only approval granted.** Nothing in this packet is applied to this tree; D2–D9 are not automatically approved. Protected files, the manifest, worker permissions, global settings, Hermes, Run 4 and SecondBrain are untouched.

## 1. What the packet does

- **P1 — inert staging** (apply first): registers the capability and the deterministic UI mapping, adds task-scoped skill delivery code and its tests. Taste is `adoption: benchmark`, so **nothing is selected and `ui_design` fails closed** (blocked plan) until P2. No behavioural change for any existing task type (tested).
- **P2 — activation** (separate approval, only after the isolation harness and live checks below): flips `taste-skill` to `adopted` (+ lock status `task-scoped`, skills.yaml `configured`). After P2 a `ui_design` task plans to claude-code with `taste-skill` (art direction) and `playwright` (visual QA); Codex stays excluded.
- Delivery is **per task into the worker's own worktree**, never `skills/`, `~/.claude`, `~/.codex`, OpenCode or Hermes (supersedes `installation-packet.md` §4c). The skill copy and `.taste-skill/` are moved/removed before the worker's changes are computed, so they can never be committed; **no git configuration is touched** (a design flaw I found in my own first version: `git rev-parse --git-path info/exclude` is shared by linked worktrees and the main checkout; it is now covered by a regression test).

## 2. Exact changes

Patch files (relative paths, apply from the repo root): `P1-inert-staging.patch` (666 lines), `P2-activation.patch` (74 lines). Resulting manifests: `P1-resulting-protected-manifest.json` (79 entries), `P2-resulting-protected-manifest.json` (79). Current manifest: 78.

| path | in protected manifest now | step | what | sha256[:16] now | after P1 | after P2 |
|---|---|---|---|---|---|---|
| `config/capability_registry.yaml` | YES | P1,P2 | registry | d094a61ceeba2db2 | b6ea1c0f97c44e29 | 90111d627d34a858 |
| `evals/test_capability_registry.py` | YES | P1 | pinned provider set | 05c01ca150ea30ca | 90eadda1e5e366f1 | 90eadda1e5e366f1 |
| `evals/test_wave_c1_production.py` | YES (evals/ glob once refreshed) | P1,P2 | new gate tests (20) | (new) | a31b288fcb1b05e3 | e608baff7d8e958d |
| `config/routing.yaml` | no (policy/dispatch: held per owner instruction) | P1 | ui_design class | 7fdd4e13f1d1ef6f | bb449494c638a9e2 | bb449494c638a9e2 |
| `agentos/skill_delivery.py` | no (policy/dispatch: held per owner instruction) | P1 | new module | (new) | d590906d5d06301b | d590906d5d06301b |
| `agentos/capability_policy.py` | no (policy/dispatch: held per owner instruction) | P1 | deliverability + selected_skills | 31e6d2349e3f11b6 | 223f230c8d8e7025 | 223f230c8d8e7025 |
| `agentos/dispatch.py` | no (policy/dispatch: held per owner instruction) | P1 | provision / instruct / finish | aa0e2b191a46bc35 | 1333b1c29e0be827 | 1333b1c29e0be827 |
| `scripts/runtime/skills.lock.json` | no | P1,P2 | delivery block; status | 030c5894ebc4df57 | 6cd6cc26f0ad5bbb | 01628b115c087b36 |
| `config/skills.yaml` | no | P2 | status candidate to configured | 43f9bdfa82f8f22f | 43f9bdfa82f8f22f | cc78a8ef578d3018 |
| `scripts/runtime/test_skills_lock.py` | no | P2 | status expectation | e623b92cdf89f134 | e623b92cdf89f134 | ced6f1ea8d6c261d |

Reviewer's guide to P1:
- **registry**: capabilities `ui.art_direction`, `ui.visual_qa`; `playwright` also declares `ui.visual_qa`; providers `taste-skill` (`benchmark`, `requires: [devops.shell]`, probe = vendored SKILL.md), `frontend-design` and `ui-ux-pro-max` (both `future`, i.e. not selectable); claude-code integration `taste-skill: supported`, codex `taste-skill: unknown`; `policy.capability_preferences` (`ui.art_direction: [taste-skill, frontend-design, ui-ux-pro-max]`, `ui.visual_qa: [playwright]`); `policy.task_types.ui_design: [ui.art_direction, ui.visual_qa, code.edit, code.test]`.
- **routing.yaml**: new task class `ui_design` (cloud, claude_subscription, worker claude_code; reviewer rule as `coding`). Not manifest-protected but policy, so it is here.
- **capability_policy.py**: `worker_deliverable` gains a `kind == "skill"` branch; `selected_skills()`. Skills without a lock `delivery` block (Ponytail, Orchestra, ambient) return deliverable, so existing plans are identical (tested).
- **dispatch.py**: `skill_ids` from the plan; provision before launch; explicit instruction line prepended; `finish()` in a `finally` around the runner call; provisioning failure ⇒ task closed `blocked`, worker never started; result gains `capabilities.skills` / `skill_evidence` only when a skill was selected.
- **skill_delivery.py** (new, stdlib + PyYAML): lock verification, provision, instruction, finish.
- **skills.lock.json**: adds the `delivery` block (src, worktree_ignore, requirements); `status` stays `dormant` in P1.
- **tests**: `evals/test_wave_c1_production.py` (20 tests) and one pinned-set edit in `evals/test_capability_registry.py` (the existing test pins the exact provider set; three new providers must be added to it).

## 3. Validation performed (on isolated scratch copies, never on this tree)

| Check | Result |
|---|---|
| `git apply --check P1` against this real tree | clean (nothing applied) |
| P1 then P2 applied in sequence to a pristine copy | clean; all 10 files byte-identical to the validated states |
| New tests | 20 passed after P1; P2 variant passes with the intended inversions |
| Mutation checks | no cleanup ⇒ 3 fail; `deliverable` always true ⇒ 2 fail; write to shared exclude ⇒ 1 fails |
| `agentos validate` | config valid after P1 and after P2 |
| Full scratch regression after P1 and after P2 | 944 passed, 2 failed, 18 skipped; **the same 2 fail on a pristine scratch copy** (`test_hermes_integration::test_wiring_and_bypass_detection_logic`, `::test_wire_script_apply_verify_rollback_on_copy`: they compare against the real repo path and live Hermes config). This tree's own baseline is 932 passed, 3 skipped. **After applying, the real-tree regression must be re-run; the scratch result is a proxy, not that run.** |
| Plan behaviour | before P2: `ui_design` blocked (`capability-missing`); after P2: claude-code only, taste-skill + playwright, `extra_mcp=[playwright]`, Codex rejected (`integration-unknown`) |

NOT validated: any live worker run; dispatch under a real Claude worker with the skill present; Codex; Hermes visibility (not needed, Hermes never sees the skill); execution isolation.

## 4. Risk analysis

| # | Risk | Severity | Mitigation / residual |
|---|---|---|---|
| R1 | Registry additions change planning for existing tasks | low | new providers are `benchmark`/`future` (never selected); `coding` mapping unchanged and tested; pinned-set test updated |
| R2 | `worker_deliverable` skill branch alters existing skill providers | low | predicate returns True unless the lock entry has a `delivery` block; tested for ponytail, superpowers, orchestra-research |
| R3 | New code in `dispatch()`, the central execution path | medium | all new code is behind `if skill_ids`; absent key keeps the old result shape (tested); fail-closed; `finally` cleanup; the two existing dispatch suites pass in scratch |
| R4 | The worker runs a third-party skill's scripts (headless Chrome, Node) with the profile's unrestricted Bash | **high until isolation exists** | deny patterns are not a sandbox. Gate rule: no executing gate and **no P2 activation before an isolation boundary exists** (D10) |
| R5 | `~/.taste-skill/history.json` written outside the worktree by `draw.mjs` | low | non-secret; D4 still open (accept, or set `TASTE_SKILL_HISTORY` through a wrapper — a protected-adjacent launch change not in this packet) |
| R6 | Prompt-injection through 39.5 KB of third-party skill prose | medium | provenance pinned by hash, verified at plan and at provision, copy re-verified; any bump needs re-review |
| R7 | Skill use cannot be proven from the `json` worker output | medium | evidence is filesystem artifacts + the explicit instruction; a launch-format change (`workers.yaml`/`workers.py`) is protected and excluded (D12) |
| R8 | `ui_design` vs `coding` is chosen by Hermes (a model) | low | a wrong choice means no art-direction skill, never a wrong one; no UI intent rule proposed |
| R9 | Manifest refresh changes protected entries (78 → 79) | low | established workflow, recorded approval first; resulting manifests and hashes listed above |
| R10 | Evidence artifacts persist under `state/tasks/<id>/evidence` | low | git-ignored task state; contains screenshots of generated pages only |

## 5. Apply procedure (only after a recorded approval; mirrors the Run 3 / rollout workflow)

1. Write `audit/wave-c1/APPROVAL.md` naming the exact patch hashes below and the decisions taken (agent-written from your instruction, as before).
2. `git apply --check audit/wave-c1/protected-packet/P1-inert-staging.patch && git apply …`
3. `uv run agentos validate`; `uv run agentos manifest` (expected: the listed protected files differ); `uv run agentos manifest --write`; compare the new manifest to `P1-resulting-protected-manifest.json`.
4. `uv run pytest evals scripts/runtime -q` (expect this tree's baseline + 20 + 9 lock tests) and `uv run python scripts/verify_skills_lock.py`.
5. P2 only on its own approval, after D10 and the live checks in §7; same steps with `P2-activation.patch`.

## 6. Rollback

P1: `git apply -R P1-inert-staging.patch`; `uv run agentos manifest --write` (under recorded approval) to return to 78 entries; D1 staging stays dormant. P2: `git apply -R P2-activation.patch` (one-line adoption flip back to `benchmark`). Task-scoped delivery leaves nothing in host or Hermes directories, so no host restore is needed; evidence under `state/tasks/*/evidence` can simply be deleted.

## 7. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D2 | Apply **P1** (protected registry/test edits + manifest 78→79 + policy/dispatch/routing code) | yes, if D10 is on the roadmap; inert on its own |
| D10 | **Isolation harness** for gates that run a model with skill scripts: Docker `--network none` with Chromium in the image, or a `sandbox-exec` Seatbelt profile (both binaries present, neither configured) | required before any executing gate and before P2 |
| D11 | **Dependency-install policy** for real React/TS gates (`npm ci --ignore-scripts` from a lockfile via an explicit mirror, inside the boundary) | required for gates 2, 5, 6 |
| D5' | **P2 activation** | only after D10, a live `ui_design` dispatch check on a scratch repo, and gate 1 repeats (n ≥ 3, blind-rated) with `draw.mjs` evidence |
| D12 | Skill-use evidence via `stream-json` worker output (protected `workers.yaml`/`workers.py`) | optional; separate packet |
| D13 | Verify (or implement) enforcement of "reviewer differs from primary" in `dispatch`/`router` | yes, before gate 4 |
| D3/D4/D6–D9 | as in `installation-packet.md` §7 (`assets.mjs` excluded; history path; evidence funding; credentialed services stay NOT TESTED; Superpowers patch; no frontend-design staging) | unchanged |

## 8. Artifact hashes (sha256)

- `P1-inert-staging.patch` `f4cb17fae7f9ac136e0ba065087cf802e5d8c1e6f8d680701988ab71756e0943`
- `P2-activation.patch` `4fa89c027f69bf64997390134b10c5ec1d6ca19a103c976993cb04c16c623e5a`
- `P1-resulting-protected-manifest.json` `c95b89b4b173801c925bb6ac4dec6b35affd1bda73d26f74b9b15371a7cee02e`
- `P2-resulting-protected-manifest.json` `589027f4c9391c36312399c1471809d504a2a16708549cd150bff376c4ed24da`

---

## Addendum — P1b: symlink / FIFO hardening of `agentos/skill_delivery.py` (APPLIED 2026-10-25; was a precondition for P2)

**Finding (automated security review, confirmed by test):** `finish()` and `provision()` run in the host dispatcher over a worktree the *worker* controls. In the applied P1 version, a planted symlink could make `finish()` copy a host file into the task evidence directory (`.taste-skill/x -> <host file>`), a symlinked `.claude`/`.claude/skills/<name>` left by an earlier attempt could redirect `provision()`'s `copytree`/`rmtree` outside the worktree, a FIFO in `.taste-skill/` could hang the dispatcher, and file count/size were unbounded.
**Exposure today: none in practice.** `selected_skills()` returns `()` until Taste is adopted (P2), so no dispatch can reach this code. It is nonetheless inside the applied P1 artifact, so I did **not** edit it in place; the fix is this separate, validated patch.

**Fix:** symlink components on the skill path are removed *as links* and never followed; `finish()` walks with `followlinks=False`, copies only regular files opened with `O_NOFOLLOW`/`O_NONBLOCK` after an `fstat` check, skips symlinks/FIFOs/devices (recorded in a new `skipped` list), and caps evidence at 200 files and 25 MB each; a non-directory where a directory is required is refused; destinations are checked to stay inside the worktree; `verify()` also rejects a symlink inside the vendored tree. Python 3.11-compatible (no 3.13-only APIs).

| Check | Result (scratch copies of the real tree; nothing applied) |
|---|---|
| New adversarial tests (9) + the 20 existing | 29 passed |
| Same new tests against the **original applied** module | **7 of 9 fail** (file-symlink leak, symlinked working dir, FIFO hang, caps, `.claude` symlink, symlinked skill dir, vendored-tree symlink); 2 already held on Python 3.11 (directory symlinks not descended; regular file where a directory is needed) |
| Full scratch regression | 956 passed; the same 2 environment-only failures as a pristine scratch copy |
| `git apply --check` on the real tree | clean |
| P1b then P2 in sequence | clean; 90 targeted tests pass |
| Manifest | one protected file changes (`evals/test_wave_c1_production.py`); entry count stays 79 |

Artifacts: `P1b-skill-delivery-hardening.patch` (273 lines) sha256 `0612f50add4433375b6022a1a80254ce18a5016bf033122616c591fc925f42db`; `P1b-resulting-protected-manifest.json` sha256 `c73a2128a2473e18bd777f038b7adb190f31c17f2105979a8be59a77430db624`. Hashes after P1b: `agentos/skill_delivery.py` `7bdb62b2cd4cac8d`, `evals/test_wave_c1_production.py` `368dba6113cddf5b`.
**Decision D15:** apply P1b (recommended, small, and required before P2 or any worker run that provisions a skill). It follows the same workflow: recorded approval, `git apply`, `manifest --write`, full regression.
Residual: a worker that races `finish()` while still running (e.g. after a timeout that failed to kill its process group) is not addressed by file checks; `O_NOFOLLOW` covers the final path component only, which is why parent components are cleared first.
