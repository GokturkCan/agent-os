# Capability rollout — protected-file approval packet, REVISION 2 (PROPOSED, NOTHING APPLIED)

Supersedes revision 1 (diff sha256 `dca775ac…`, which is no longer valid). Prepared 2026-10-25 on `feature/capability-rollout`
(base `main` a2c0897; `feature/run4-research-plane` untouched at a2c0897). Real repo: no protected file modified, `agentos manifest`
→ "protected files match manifest". Everything below was built and tested in an isolated copy.

**Exact artifacts (this folder)**
| File | Lines | sha256 |
|---|---|---|
| `capability-rollout-protected-packet.diff` (the packet to approve) | 885 | `4394aca527d8899ff58938f2b3fa58ba34d3075310d5cfe2806daf10988ffc5b` |
| `capability-rollout-companion-code.diff` (UNPROTECTED code that belongs with it) | 87 | `0345f1dfd23226d13154a53b95c5d4cd7dd0dc3b2689526e85e1782cc704acab` |
| `capability-rollout-apply-protected.py` (applier: `python … ROOT --o1 --o2`) | | |
| `capability-rollout-test_capability_rollout.py` (new protected test, 42 tests) | | |

## 1. What changed since revision 1 (and why)
* **GitHub fail-closed redesigned.** Rev 1 marked integrations `unsupported` in the registry. Running the full suite showed that
  this changes registry facts that three frozen SystemOne/Open-Jev tests check (`test_capability_labels_match_the_registry` x2,
  `test_missing_capabilities_use_the_capability_plane_integration_logic`). Rev 2 leaves **every registry integration fact unchanged**
  (GitHub MCP stays healthy and `supported` for the harness) and enforces *deliverability* where dispatch plans.
* **`security` deny scope tightened**; ineffective `Bash(*/gh:*)` removed (it did not match absolute paths in a real worker).
* New explicit policy key `withheld_executables: [gh]` in `workers.yaml` (found necessary: Codex has no deny list, so a deny-pattern-only
  rule left Codex eligible for `gh-cli`).

## 2. Protected change list = manifest delta (9 paths; 77 → 78 entries)
| Path | Kind | +/- | Class |
|---|---|---|---|
| `config/mcp.yaml` | modify | +34/-17 | Mandatory |
| `config/capability_registry.yaml` | modify | +121/-22 | Mandatory |
| `config/workers.yaml` | modify | +16/-3 | Mandatory (`gh` deny, `withheld_executables`, versions) |
| `agentos/workers.py` | modify | +13/-1 | Requested defense-in-depth (separable; drops 4 tests) |
| `evals/test_a3_web_docs.py` | modify | +3/-3 | Mandatory (3 router outcomes move) |
| `evals/test_capability_probes.py` | modify | +6/-1 | Mandatory (keeps the "failing → unhealthy" mapping covered synthetically) |
| `evals/test_capability_registry.py` | modify | +12/-3 | Mandatory (provider/adoption inventory) |
| `evals/test_capability_wiring.py` | modify | +4/-3 | Mandatory (Playwright pin; GitHub task now NOT dispatched) |
| `evals/test_capability_rollout.py` | **new** | 273 lines | Mandatory |
`evals/test_capability_acceptance.py` is **no longer touched** (rev 1 changed it; rev 2 does not need to).
Optional extra inside `workers.yaml`: the `security` CLI deny (included in the diff above with `--o2`; drop by applying without `--o2`).

**Companion UNPROTECTED code (not in the manifest; reviewed here because behavior depends on it):**
`agentos/capability_policy.py` (+27/-2: `plan(..., deliverable=None)` and `worker_deliverable(cfg)`, wired into `plan_for`),
`agentos/capability_registry.py` (+1/-1: reason code `integration-undeliverable`), `agentos/capability_cli.py` (+1/-1: `capabilities match`
uses the same predicate so the diagnostic never contradicts dispatch).

## 3. Review of the eight mandatory points
1. **Worker-only GitHub restrictions, not a sandbox.** Deny patterns + launch-env isolation apply to *automatically dispatched* workers only
   (per-launch `--disallowedTools` argv and launch env; nothing is written to any settings file — asserted by a test). Wording in
   `workers.yaml`, `workers.py`, `docs/capability-rollout.md` says "defense in depth, NOT a sandbox".
2. **Residual macOS Keychain risk (accounted for, nothing retrieved).** I did not run `gh auth token` or read any credential. Earlier I only
   observed an exit code (rc 0) that proves the keyring fallback *exists*; its output was discarded. Facts: (a) Claude workers: any command
   text not matched by a pattern still runs as the user, so a determined/prompt-injected worker is not contained — patterns are best-effort;
   (b) with isolation, `gh api`/`gh pr` fail (observed rc 1/4); (c) **Codex (observed 2026-10-25, one run, `workspace-write`):** `gh` reported
   "not logged in", `curl` could not resolve any host (no network), and `security list-keychains` failed — so the Codex sandbox appeared to block
   network and keychain access. One observation, not a guarantee. Mitigation/limit: keep read-only GitHub access through the MCP only.
3. **GitHub tasks fail closed, MCP not marked broken.** `plan_for` (used by dispatch and `capabilities match`) treats a tool as *deliverable*
   only if an MCP has a `launch` in `mcp.yaml` and a CLI is not withheld/denied for that worker. Result with everything healthy:
   `devops.github` → no executor → `not_dispatched / blocked / human handoff`, reason `integration-undeliverable`; `gh-cli` is never a fallback;
   pure `plan()` (registry semantics, SystemOne options, frozen datasets) is unchanged; GitHub MCP stays healthy and `adopted`.
   Invariant test: any executor-supported MCP without a launch must be reported undeliverable.
4. **Optional `security` CLI restriction — recommended, scope-limited.** Patterns: `Bash(security:*)`, `/usr/bin/security`, `env security`, and verb globs
   (`find-`, `dump-`, `export`, `add-`, `delete-`, `list-`). They travel only in the dispatched Claude worker's `--disallowedTools`; interactive Claude
   Code, Codex and OpenCode are unaffected. Verified with a real worker: `security list-keychains` in 5 spellings and a not-found
   `find-generic-password` were denied; `ls docs/security-permissions.md`, `grep -c security README.md`, `git status`, `echo through the night` ran.
   Cost: dispatched workers cannot use the macOS `security` tool (code-signing/keychain tasks) — none exist in Agent OS today.
5. **Interactive permissions preserved.** `~/.claude/settings*.json`, `~/.codex/config.toml` (see §6), `~/.config/opencode/opencode.json` are not edited by
   the packet; skill directories keep 91 links each; modification times of Claude/OpenCode settings predate this work.
6. **Run 3 approval history — real evidence found.** PR #7 comment `issuecomment-6295350672` by GokturkCan, 2026-10-20T16:06Z (merge 16:12Z),
   explicitly approves the Run 3 delta at `d77d6b0` (38 added, 2 modified, manifest 39→77) and states it is **not** approval of future protected
   changes. Historical documents keep their original PENDING wording (nothing rewritten); the manifest `note` text is regenerated by
   `agentos manifest --write`, which resets it to the generic sentence. **That Run 3 approval does not cover this packet.**
7. **Dormant tools untouched:** OpenSpec 0.17.2, OmniRoute 3.8.50, clawdbot 2026.1.23-1 (npm), SuperClaude 4.1.9 (pipx): versions unchanged, no
   process/listener. Registry records them honestly (`benchmark`/`disabled`).
8. **Not touched:** Hermes configuration (see note), SecondBrain (health: doctor ok, lint 0), MSI, Open-Jev, FastGate/SystemOne config.

## 4. Behavior changes you are approving
1. Router: `github_structured → github_mcp`; `file_to_markdown → markitdown`; `repo_packing → repomix`.
2. A `devops.github` task is not dispatched to any worker (human handoff). Closing that later needs a launcher that can deliver HTTP + headersHelper
   servers (protected `workers.py`); not in this packet.
3. `rea` stays `adopted` (Run 2 scenarios S8/dispatch-blocked encode it; unavailable ⇒ never selected).
4. Deny over-blocking: any command containing `gh auth`, `gh api`, or the listed `security` verbs is refused (text match).
5. Dispatched worker env carries empty `GH_*` token variables and `GH_CONFIG_DIR=state/runtime/gh-isolated` (created 0700) for Claude and Codex.

## 5. Evidence (isolated copy)
* `agentos validate` → config valid. Manifest drift = exactly the 9 paths above.
* **Full suite on the patched copy: 914 passed, 18 skipped, 3 failed** — the 3 are artifacts of the copy (no `.git`, repo-path comparison) and pass on the real
  repo; with a git index the invariants test (no `/Users/…` in tracked source) passes against the packet's files.
* The three frozen SystemOne label tests that rev 1 broke now pass.
* Real headless workers built from the patched config: gh/security spellings denied as listed; controls ran. Real Codex run: observations in §3.2.

## 6. Side effects of my testing you should know about
* **`~/.codex/config.toml`**: my Codex sandbox test (run with a temporary working directory) caused Codex to add a project-trust entry
  `[projects."/private/var/folders/…/tmp.kXw3l08Rh4"]` for that now-deleted directory. Harmless but unintended. I did **not** remove it; remove that one
  section yourself or authorise me to (decision D7).
* **`~/.hermes/config.yaml`** modification time is 2026-10-24 20:58. A routine `agentos health` and the Hermes skill probe were each re-run and do *not*
  change it; Hermes is live (its state DB was written minutes ago). Cause unattributed; contents deliberately not read.

## 7. Rollback
Nothing applied → nothing to roll back. After applying: `git checkout -- <9 protected paths> agentos/capability_{policy,registry,cli}.py`,
`rm evals/test_capability_rollout.py`; if the manifest was refreshed: `git checkout -- evals/protected-manifest.json`; `agentos manifest` must report a match.

## 8. Procedure after approval (exactly)
1. Apply the packet (`--o1`, and `--o2` only if D3 is yes); copy the new test; the companion code is applied by the same script.
2. Run the affected test files once, then `agentos validate`.
3. Write the machine-readable delta (`audit/capability-rollout-protected-delta.json`) and approval note; run `agentos manifest --write` **only after your
   approval is recorded outside the manifest** (the Run 3 pattern: a PR comment — I will not create the PR before your separate authorization, so
   the recording place is your call, D6).
4. Verify routing: markitdown / repomix / GitHub MCP, GitHub fail-closed, Orchestra index and Ponytail loading; one final regression.
5. Flip docs PENDING → APPLIED only where verified; prepare a clean staged list; STOP for commit authorization.

## 9. Decisions I need
* **D1** Approve this exact packet (protected diff sha256 `4394aca5…` and companion diff `0345f1df…`)?
* **D2** Include `agentos/workers.py` credential isolation (recommended yes)?
* **D3** Include the `security` deny (recommended yes)?
* **D4** Accept "GitHub tasks are not dispatched to workers" (§4.2)?
* **D5** Accept `rea` staying `adopted` (§4.3)?
* **D6** Where do you want the approval recorded for the manifest refresh (e.g. a comment on the PR once it exists, or a signed note in `audit/`)?
* **D7** Remove the stray Codex trust entry for the deleted temp directory (you, or me)?
