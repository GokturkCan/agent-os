#!/usr/bin/env bash
# Read-only + dry-run Hermes/Agent OS smoke checks after hermes-wire apply.
# Usage: AGENTOS_REPO=/Users/gokturkcan/agent-stack-integration ./scripts/hermes-smoke.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AGENTOS_BIN="${AGENTOS_BIN:-$ROOT/bin/agentos}"
export PYTHONPATH="${PYTHONPATH:-$ROOT}"

echo "== Agent OS entry =="
"$AGENTOS_BIN" intent --text "what did we decide about Agent OS architecture?"
"$AGENTOS_BIN" intent --text "fix the failing test in this repo"

echo "== Knowledge recall (read-only) =="
"$AGENTOS_BIN" recall "Agent OS control plane" --top 3 | head -40

echo "== Project registry =="
"$AGENTOS_BIN" knowledge projects | head -20

echo "== Continuity (real repo; no vault writes) =="
"$AGENTOS_BIN" knowledge status --project prj-9c588b6b1fd1ce3f1b1d --repo "${AGENTOS_REPO:-$HOME/agent-stack}" | head -40

echo "== Hermes bridge =="
PYTHONPATH="$ROOT" "${PYTHON:-python3}" -c "
from agentos import hermes_bridge as hb
print('skills_dir', hb.SKILLS_DIR)
print('canonical_external', hb.canonical_external_skills_dir())
print('is_wired', hb.is_wired())
print('entrypoint', hb.entrypoint_status())
"

echo "== Dispatch dry-run (development path) =="
"$AGENTOS_BIN" dispatch --task-id smoke-dry --type coding --repo "${AGENTOS_REPO:-$HOME/agent-stack}" \
  --prompt "read-only smoke: do not modify files" --verify "true" --dry-run | head -20

cat <<'NOTE'

Live Hermes (after hermes-wire apply --i-approve):
  bin/hermes-agentos "What do we know about Agent OS?" 
  bin/hermes-agentos "Remember for Agent OS: weekly scheduling review is our cadence."
  bin/hermes-agentos "Where did we stop on Agent OS?"

Knowledge capture still requires authorized JSON + agentos knowledge capture (no auto vault apply).
NOTE