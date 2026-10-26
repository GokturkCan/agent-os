# Wave C1 — dependency policy for gate fixtures (D11: offline-first, pinned lockfile)

2026-10-25 · Policy document only. Nothing was installed, no cache was populated, no registry was contacted. Scope: the real React/TypeScript fixtures of acceptance gates 2, 5 and 6 (not yet built). Applies to nothing else in Agent OS.

## 1. Facts on this machine

node v24.21.0, npm 11.19.0; pnpm, yarn and bun are absent (npm is the only package manager; this policy does not introduce another). Precedent: the pinned repomix runtime (`scripts/runtime/repomix/package-lock.json`, installed with `npm ci` into `state/runtime/repomix`, ignored by git): lockfileVersion 3, 172 packages, **0** with install scripts, **0** without a registry URL and sha512 integrity. So the rules below are realistic and machine-checkable on a real tool lock.
npm inside the L1 harness was exercised only on a zero-dependency project (`npm install --package-lock-only` and `npm ci --offline --ignore-scripts` both exit 0, lockfileVersion 3); no package was downloaded.

## 2. Three phases; only the first may touch the network

| Phase | Where | Network | What runs | Output |
|---|---|---|---|---|
| **F — fetch** | host, by a human-started command, on a scratch directory containing **only** `package.json` + `package-lock.json` (no project source) | registry host only (`registry.npmjs.org`), by explicit `NPM_CONFIG_REGISTRY`; never through the worker | npm itself with `--ignore-scripts --no-audit --no-fund` populating a cache directory | `state/runtime/npm-cache/<fixture-id>/` (git-ignored) and a recorded list of tarball integrities |
| **I — install** | L1 sandbox (`wave-c1.sb`), worktree as `WORK` | **none** | `npm ci --offline --ignore-scripts --no-audit --no-fund` with `NPM_CONFIG_CACHE` = a copy of the phase-F cache placed under `TMP` | `node_modules` inside the worktree |
| **R — run** | L1 sandbox | **none** | `tsc --noEmit`, `eslint`, `vitest`, build, deterministic checkers | results |

Rationale: install-time code execution and network are the two ways a dependency tree reaches the host. Phase F runs no project and no dependency code (scripts disabled, no source present). Phases I and R have no network, so a compromised package cannot exfiltrate or fetch more.
`npm ci` already verifies each tarball against the lockfile's sha512 `integrity` and refuses a lock/package.json mismatch; this is npm's documented behaviour and is **not** independently tested here.

## 3. Lockfile admission rules (all checkable by a small stdlib script; the script does not exist yet)

A fixture lockfile is admitted only if **all** hold:
1. `lockfileVersion` is 3.
2. Every package entry has `integrity` starting `sha512-` and `resolved` starting `https://registry.npmjs.org/`. No `git+`, `github:`, `http:`, `file:`, `link:`, tarball URLs, or aliases to other registries.
3. `package.json` dependencies use **exact versions** (no ranges, `latest`, tags, or `workspace:`/`*`).
4. No package with `hasInstallScript: true` unless allowlisted by exact `name@version` with a written reason (their scripts are never run: `ignore-scripts=true` is enforced by flag **and** by `NPM_CONFIG_IGNORE_SCRIPTS=true`). A package that cannot work without its install script (binary download such as browsers, `sharp`-style fetchers) is **out of scope for gate fixtures**.
5. No `peerDependencies` auto-installed outside the lock (npm 7+ installs them; the lock must already contain them).
6. Size budget declared per fixture (suggested ≤ 400 packages, ≤ 250 MB `node_modules`); exceeding it needs a written reason.
7. Provenance review by a human before first admission: the direct dependency list (name, version, weekly-downloads sanity, repository, licence) is recorded next to the lock. **Package-age quarantine** (no version published in the last 7 days) needs registry metadata and therefore belongs to phase F; it is a stated requirement but not implemented.

## 4. Environment and configuration rules

- `NPM_CONFIG_USERCONFIG` and `NPM_CONFIG_GLOBALCONFIG` point at two **distinct empty files** inside the sandbox (the same path for both makes npm error: "double-loading config"). The real `~/.npmrc` (which may hold registry credentials) is never read: the home directory is not readable in L1 and `HOME` is the worktree.
- `NPM_CONFIG_CACHE` is under `TMP` (writable) for I/R, and a dedicated directory for F. `NPM_CONFIG_UPDATE_NOTIFIER=false`, `NPM_CONFIG_AUDIT=false`, `NPM_CONFIG_FUND=false`.
- No auth token is ever placed in the fixture, the cache, the environment, or the sandbox.
- The cache is **read-only input** to phase I (copy, never mount writable); the cache of one fixture is never reused for another.

## 5. Gaps, stated precisely (nothing below is implemented)

| # | Gap | Consequence | Smallest fix (not applied) |
|---|---|---|---|
| D11-1 | No lockfile admission script | rules in §3 are only a document | stdlib Python `scripts/lint_npm_lockfile.py` + tests (unprotected files) |
| D11-2 | No phase-F tool | cache cannot be populated reproducibly | a documented command sequence run by a human; the script above prints the integrity list |
| D11-3 | No fixtures and no lockfiles | gates 2/5/6 have nothing to install | build fixtures later; each needs a one-time human provenance review |
| D11-4 | Offline install with a real tree is untested | only a zero-dependency `npm ci` was exercised | first fixture's phase I run inside L1, as a deterministic (non-LLM) check |
| D11-5 | Browser binaries (Playwright/Chromium downloads) are install-script based | browser-based fixtures cannot get a browser from npm | use the already-installed Chrome / the adopted Playwright MCP; see the isolation proposal for the unresolved browser-in-sandbox problem |
| D11-6 | Registry compromise before first admission | a malicious pinned version would be admitted | human review (§3.7), age quarantine (§3.7), and phases I/R having no network limit the blast radius; not eliminated |
| D11-7 | npm lifecycle scripts still exist for *project* scripts (`npm test`) | a fixture's own scripts run code | they run only in L1 (no network, worktree-only writes); they are fixture-authored, not third-party |

No change to any protected policy is proposed by this document.
