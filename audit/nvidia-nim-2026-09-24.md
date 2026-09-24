# NVIDIA NIM / DeepSeek Harness Provider Audit — 2026-09-24

**Supersedes:** `audit/nvidia-nim-2026-09-23.md` (kept as historical evidence — the
Kimi K3 failure it documents is still true and still relevant; it is not
deleted, only superseded as the *current* provider verdict).

**Scope:** Validated a different model/harness combination on the same
provider. This is new evidence about NVIDIA NIM as a provider, not a retest
of Kimi K3.

---

## What was validated

| Component | Value |
|---|---|
| Model | `deepseek-ai/deepseek-v4.1-flash` |
| Provider | NVIDIA NIM Free Endpoint |
| Harness | DeepSeek Harness (full SDK/runtime, stateful, retry-capable) |
| Profile | high reasoning |
| Task | 20-step autonomous repo-debugging run |

## Result: PASS

- Total wall time: 2697.406 s (~44m57s)
- Provider timeouts: 2 × ~300s
- Automatic retries: 2
- State loss: 0
- Fatal session failure: 0
- Final suite: 8/8 PASS
- Repeated stability: 5/5 runs PASS
- Baseline regression independently reproduced
- No async task leaks
- Dirty user work preserved throughout

## Benchmark conditions (important caveat)

This was a **vanilla** run — no Hermes orchestration, no MCP, no subagents,
no specialist skills, no repo RAG, no external verifier. The numbers above
describe the model+harness+provider combination in isolation, not its
performance inside the full Agent OS stack. Any future comparison against
Hermes-orchestrated runs must preserve this distinction.

## Interpretation

- **DeepSeek V4.1 Flash** = validated strong autonomous coding specialist.
- **DeepSeek Harness** = validated stateful/retry-capable coding harness —
  it absorbed two provider-side timeouts with automatic retry and zero state
  loss.
- **NVIDIA NIM** = a useful strong free compute/provider for this workload.
  It is **not** a latency-sensitive interactive primary backend. It is a
  background / escalation / specialist provider.

Do not infer from this that NVIDIA NIM is the default Hermes brain. It
remains a specialist provider for a specific task shape:

- hard repo debugging
- concurrency bugs
- long-horizon coding
- refactoring
- regression repair
- code verification
- background engineering

## Relationship to the 2026-09-23 audit

The previous audit found NVIDIA NIM connectivity/auth working but
`moonshotai/kimi-k3` unreliable (0-byte responses on chat and streaming).
That finding stands — it was a different model on the same provider. This
audit does not contradict it; it adds a second, validated data point:
NVIDIA NIM's serving path is reliable for at least one model
(`deepseek-ai/deepseek-v4.1-flash`), so the provider itself is not the
limiting factor — model/backend choice on NIM is.

## Current policy

- NVIDIA NIM: enabled, scoped to background/escalation coding specialist use
  (see `config/providers.yaml`, `config/models.yaml`, `config/routing.yaml`).
- `moonshotai/kimi-k3`: still not to be treated as reliable (unchanged from
  2026-09-23).
- `deepseek-ai/deepseek-v4.1-flash` via DeepSeek Harness: adopted as a
  background/escalation coding specialist, not as a primary interactive
  worker and not as a second global orchestrator.
