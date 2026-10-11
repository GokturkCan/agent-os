# Roadmap

Legend: **IMPLEMENTED** code exists · **VERIFIED** exercised by tests or a real run ·
**PARTIAL** some of it works · **DESIGN-ONLY** written down, no code.
Only claims backed by `CURRENT_STATE.md` are marked VERIFIED.

## Run 1 — Core Agent OS (V1)

| Item | State |
|---|---|
| Config as source of truth + validation | IMPLEMENTED, VERIFIED |
| Deterministic routing and intent classification | IMPLEMENTED, VERIFIED |
| Canonical front door + structural mutation branch | IMPLEMENTED, VERIFIED (real mutation acceptance) |
| Task state, worktrees, leases | IMPLEMENTED, VERIFIED |
| Retry / resume | IMPLEMENTED, VERIFIED (real failure → retry → resume) |
| Worker/verifier timeout enforcement | IMPLEMENTED, VERIFIED by tests; **real acceptance PENDING** |
| Verification loop | IMPLEMENTED, VERIFIED |
| Telemetry + lifecycle events | IMPLEMENTED, VERIFIED (no TTFT/RAM/VRAM) |
| Health / config validation | IMPLEMENTED, VERIFIED |
| SecondBrain gated memory | IMPLEMENTED, VERIFIED (fixture vaults) |
| OpenCode worker | PARTIAL (argv only, not live-verified) |
| Remaining to close Run 1 | real timeout→resume run; private-repo first release |

## Run 2 — Capability plane

| Item | State |
|---|---|
| CapabilityRegistry (discover/select tools+skills by capability) | DESIGN-ONLY |
| ContextGate (per-task context loading policy) | DESIGN-ONLY |
| Today's static equivalents (`config/capabilities.yaml`, `skills.yaml`, `mcp.yaml`) | IMPLEMENTED |

## Run 3 — Local intelligence plane

| Item | State |
|---|---|
| SystemOne fast local tier (FastGate/Laya) | DESIGN-ONLY (router skips tier) |
| Local models (Qwen3.6, Bonsai 2) | DESIGN-ONLY (benchmark candidates, nothing installed) |
| Secondary compute node (resource state machine) | PARTIAL (state machine verified; node not connected) |

## Run 4 — Research / web plane

| Item | State |
|---|---|
| Research workflow contract (`workflows/research-question.md`, `docs/research-plane.md`) | DESIGN-ONLY |
| Web/research workers, `~/research-workspaces` runtime | DESIGN-ONLY |

## Self-improvement closed loop

Target: observe → lesson → evidence → proposal → sandbox → evaluate → independent review
→ canary → promote/rollback.

| Stage | State |
|---|---|
| Telemetry/events as observation source | IMPLEMENTED, VERIFIED |
| Lesson capture, proposal gate, protected manifest | IMPLEMENTED, VERIFIED (mechanism) |
| Autonomous candidate generation, sandbox eval, canary, rollback automation | DESIGN-ONLY (intentionally absent in V1) |
