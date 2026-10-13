#!/usr/bin/env bash
# Executable eval suite. Deterministic by default; AGENTOS_LIVE=1 also runs
# the live Claude Code worker test (uses subscription quota, fixture repo only).
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --quiet agentos manifest          # protected judge/eval files must match reviewed hashes
exec uv run --quiet pytest -q -rs evals "$@"
