# Continuous integration (minimal, offline)

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`. It needs no secrets and performs no network access after the
locked dependency install (`uv sync --extra test --frozen`). It runs, in order: `agentos manifest`, `agentos validate`, the activation/security
tests, the compute fail-closed tests, the efficiency safety/recovery tests, the Open-Jev closure tests + evidence-archive verification,
the Hermes integration tests, the full regression, and a whitespace check limited to newly introduced source.

## Deliberately NOT run in CI (and why)
| Not run | Reason | How it is covered instead |
|---|---|---|
| `evals/test_laya_smoke.py` | needs the real Laya-MLX runtime and inference (git-ignored `state/runtime/`) | run locally; result recorded in the R3.2 audit |
| Live-Hermes tests (`needs_hermes` / `AGENTOS_LIVE=1`) | need `~/.hermes` on the Mac; they SKIP (visibly, `-rs`) when Hermes is absent | the logic tests, the synthetic-skill disable-list test and the archived-skill regressions run without Hermes |
| `agentos health` | probes the live host (installed worker CLIs, Hermes config, MCP auth, MSI reachability) | run locally before release; its WARN lines (e.g. GitHub MCP 401, no fallback model) are host state, not repo state |
| Real-model benchmarks / Open-Jev reruns | no weights, no inference, by policy | frozen results + archive verification |

A green CI run is **necessary, not sufficient**: it is not a security approval. Changes to protected files (`agentos manifest` lists them) still
require the human approval recorded outside the manifest; a manifest refresh is mechanical only.
