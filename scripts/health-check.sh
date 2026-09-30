#!/usr/bin/env bash
# Agent OS control-plane health check. Read-only. Exit 1 on any FAIL.
# MSI absence is reported as INFO (never a boot dependency).
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --quiet agentos health "$@"
