# Wave C1 — isolation harness proposal (D10; preparation only)

2026-10-25 · Scope: Wave C1 only. **Nothing here is wired into Agent OS, dispatch, workers, host settings or any protected file.** Files: `audit/wave-c1/isolation/wave-c1.sb` (profile) and `audit/wave-c1/isolation/canary.sh` (reproducible checks). No Docker was started or installed, no new tool was installed, no third-party skill code was run.

## 1. Verdict by layer

| Layer | What it isolates | Status | Evidence |
|---|---|---|---|
| **L1 — deterministic tool execution** (offline install, `tsc`/`eslint`/`vitest`/build, checkers) under `sandbox-exec` | filesystem, network, environment | **PROVEN for non-browser toolchain** (node 24.21, npm 11.19) | `canary.sh`: 13/13 PASS, run from the repo script; host-side verification, positive control, loopback listener saw only the control request |
| **L1b — browser QA inside L1** (Chrome headless) | same | **BLOCKED** | 3 bounded attempts. Without `--no-sandbox` and with it, Chrome fails (singleton socket bind, then crashpad). Crashpad insists on initializing under the *real* `~/Library/Application Support/Google/Chrome`; running it would need write access to the user's real browser profile, which the profile refuses. The real profile's mtime (05:33) predates every probe |
| **L2 — LLM runs (model client + its Bash)** | shell commands only, via Claude Code's native sandbox | **UNVERIFIED — not run** | Source: Claude Code docs (read, not executed). Verifying it needs a model invocation, which is not approved before isolation is verified (see D14) |
| Docker | — | **UNAVAILABLE** | client 28.1.1 present; `docker info`: daemon not running. Not started (starting Docker Desktop is the owner's action, and an image would need pulling or building) |

## 2. L1: the harness (proven)

Mechanism: `/usr/bin/sandbox-exec` (macOS Seatbelt; deprecated by Apple but present and functional), deny-by-default profile `wave-c1.sb` with parameters `WORK` and `TMP`.
- **Writes:** only `WORK`, `TMP`, `/dev/null`. **Reads:** system paths, the Homebrew `Cellar`/`opt`/`lib`/`openssl@3` trees (read-only, node's dylibs and config), `WORK`, `TMP`. Everything else, including the whole home directory, is denied by default (no home mount; the `HOME` it sees is `WORK`).
- **Network:** `(deny network*)`: no outbound, no loopback, no DNS. Loopback was explicitly tested.
- **Environment:** Seatbelt does **not** scrub the environment (canary E0 leaked a token). The harness must launch through `/usr/bin/env -i` with an allowlist (`PATH`, `HOME=$WORK`, `TMPDIR=$TMP/`, `NPM_CONFIG_USERCONFIG`/`GLOBALCONFIG` pointing at two distinct empty files, `NPM_CONFIG_CACHE` inside `TMP`). Verified: token absent.
- **Tightened by testing:** the broad `(allow mach-lookup)` I first used is *not* needed by node and was removed.
- **Known residual capability:** `sysctl-read`, `signal` to self, `process-fork`, exec of anything under `/bin`, `/usr/bin` and the Homebrew trees (so a sandboxed process can run `curl`, `python3` and so on, but with no network and the same file limits). `sandbox-exec` provides no CPU/memory/time limit: the harness must add a wall-clock cap (e.g. `perl -e 'alarm N; exec @ARGV'`). It is not an escape-proof VM boundary against kernel bugs.
- **Start directory:** start the sandboxed command with its cwd inside `WORK` (the canary showed a harmless `getcwd` error otherwise).

Reproduce: `audit/wave-c1/isolation/canary.sh <absolute base dir outside HOME>` (exits 0 only if all PASS). It refuses a base inside HOME, `~/agent-stack`, `~/SecondBrain`, `~/.claude`, `~/.hermes`, `~/.codex`, `~/.config`; creates one new `mktemp -d` directory with known files; never deletes anything; stops only the listener it started.

## 3. What each Wave C1 gate can use today

| Gate | Deterministic parts | LLM-generation part |
|---|---|---|
| 2 TS/React | offline install, tsc, eslint, vitest, build: **L1 usable** once D11 cache and a fixture lockfile exist | needs L2 |
| 3 Debugging | hidden-test scoring and revert-mutation check: **L1 usable** | needs L2 |
| 4 Review | scoring is text analysis (no execution) | needs L2 (and D13 enforcement) |
| 5 Accessibility / responsive | `check_ui.mjs`-class checks need a browser: **BLOCKED in L1** | needs L2 |
| 6 Animation | browser traces: **BLOCKED in L1** | needs L2 |
| 1 Taste | needs the model to run the skill's scripts (Chrome inspector): **BLOCKED** until a browser path and L2 exist | needs L2 |
| 7, 8 | offline/unit checks already run on the real tree | — |

## 4. Open design questions (smallest next steps, none approved)

1. **L2 verification (D14, needs your approval):** one or two *canary-only* model invocations using Claude Code's native sandbox via per-invocation `--settings` (`sandbox.enabled`, `failIfUnavailable: true`, `allowUnsandboxedCommands: false`, empty `network.allowedDomains`, `filesystem.denyRead` for home, plus `permissions.deny` for `Read`/`Edit`/`Write` on credential paths, because per the docs the file tools and hooks/MCP run **outside** the sandbox), with `--setting-sources project --strict-mcp-config --no-session-persistence`. The canary prompt only asks the model to attempt reading/writing fake files and a loopback port. These are not benchmark arms. Pass criterion = the same 13 canaries from inside a real model session.
2. **Browser QA path:** (a) run Chrome QA *outside* L1 through the already-adopted Playwright MCP against `file://` pages with request blocking, accepting Chrome's own renderer sandbox as the boundary; or (b) a bounded further probe for a Chrome configuration that keeps crashpad inside `TMP` (unknown whether one exists; Chrome's crashpad path is not controlled by `--user-data-dir` on macOS). Not tried further because every attempt that succeeded would require widening the profile.
3. **Wall-clock and resource caps** for L1: add to the (not yet written) wrapper; not provided by Seatbelt.
4. **Where the wrapper lives** (`bin/` like `repomix`/`markitdown`, protected-adjacent) and whether dispatch should call it: a separate packet; not proposed in this pass.

## 5. Risks of relying on this

Seatbelt is a deprecated interface and could change across macOS releases (re-run `canary.sh` after OS updates). Profiles are host-specific (Homebrew paths). L1 does not protect the model client; L2 is unverified. Until D14 passes, **no model run may execute third-party skill scripts**, and no gate that needs one may be reported as passed.
