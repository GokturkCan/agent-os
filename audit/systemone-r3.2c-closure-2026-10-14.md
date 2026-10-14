# R3.2C closure — Laya-MLX vs Strands Decider-2B vs Kev-0.8B (2026-10-14)

**Verdict: NO-GO for all three as a FastGate/SystemOne decider. No winner is promoted. Production default stays `systemone.backend: null`.**
The three backends remain configured (protected `config/systemone.yaml`) as benchmark candidates only.

## Evidence (all local, offline, $0, same frozen payload/template for every backend)
Held-out = `evals/data/systemone-heldout-v1.yaml` (sha256 3affe3b4…, 64 cases, unmodified, scored once per candidate). Dev = `systemone-decisions-v1.yaml`.
Raw JSON: `audit/systemone-eval-r3.2c/{heldout/,}{laya,decider,kev}-mlx.json`, benches `decider-mlx-bench.json`, `kev-mlx-bench.json`, `audit/laya-mlx-r3.2/run1.json`.

| Held-out, `described` variant | Laya | Decider-2B | Kev-0.8B | label-prior baseline |
|---|---|---|---|---|
| acceptable | 0.685 | **0.731** | 0.661 | 0.615 (first/last 0.561, random 0.585) |
| forbidden-choice rate | 0.115 | 0.061 | **0.054** | – |
| counter-prior acceptable | 0.542 | **0.653** | 0.528 | – |
| swap-all follows-label (lower = reads descriptions) | 0.883 | 0.830 | 0.808 | – |
| order-consistent | **0.623** | 0.264 | 0.170 | – |
| EN / TR acceptable | .667/.703 | .742/.719 | .667/.656 | – |
| escalate-gold correct, with abstain | 0.0→1.0 (recall≈1, precision 0.173) | 0.357 (prec 0.50) | **0.857** (prec 0.429; unsafe-selection 0.143) | – |
| protocol / e2e / policy suite | 149/149, 6/6 | 149/149, 6/6, 4/4 | 149/149, 6/6, 3-4/4* | – |

\*Kev with abstain: 1 safe degradation on held-out, 1 on dev (abstained where policy expected a route).

Dev (not for generalisation claims): described acceptable Laya 0.649 / Decider 0.825 / Kev 0.740; Decider swap-all 0.50 (reads descriptions on dev) but 0.83 on held-out.

| Operational (n=200, M4 16 GB) | Laya | Decider | Kev |
|---|---|---|---|
| warm p50 / p95 | 18 / 22 ms | 165 / 169 ms (decision incl. rendering 222–276 ms in eval) | 55 / 72 ms (eval 103–121 ms) |
| cold start | 0.55 s | 5.7 s | 3.0 s |
| worker RSS | 0.8 GiB | 2.7–3.0 GiB | 1.5 GiB |
| valid-choice / repeat-consistent | 100% / yes | 100% / yes | 100% / yes |

## Pre-registered gates (Phase 2A §6), held-out + dev
| Gate | Laya | Decider | Kev |
|---|---|---|---|
| G1 protocol ≥0.99 | pass | pass | pass |
| G2 swap follows-label ≤0.60 (**NO-GO if failed**) | FAIL .88 | FAIL .83 (dev .50) | FAIL .81 |
| G3 counter-prior ≥0.60 | FAIL .54 | pass .65 | FAIL .53 |
| G4 order-consistency ≥0.80 | FAIL .62 | FAIL .26 | FAIL .17 |
| G5 ≥ label-prior +0.05 | pass +.070 | pass +.116 | FAIL +.046 |
| G6 p95 ≤1 s, RSS ≤7 GiB | pass | pass | pass |
| G7 abstention precision ≥0.5 | FAIL .17 | pass .50 | FAIL .43 |

## Findings
1. All three mostly follow the option **label**, not its description (G2): they are weak at the exact property FastGate needs (contextual candidate selection). Their margin over a trivial label prior is small (+0.05…+0.12 on 64 synthetic cases; not a statistical estimate).
2. **Decider-2B** is the best on quality (acceptable, counter-prior, abstention precision), but is order-sensitive (0.26) and 10× slower/4× larger than Laya. Closest to qualifying: fails G2, G4.
3. **Kev-0.8B** is the best at *safe abstention* (recalls 86% of escalate-gold) but at the cost of 12% escalations, and has the worst order consistency (0.17).
4. **Laya** is the only operationally cheap and the most order-stable, yet the weakest at honouring descriptions.
5. Turkish quality ≈ English for all three (no language collapse), at this sample size.
6. Safety: every failure mode is an escalation, never a raise; replies are parsed by the adapter, never authority; abstain→escalate; workers run with a scrubbed env, offline, killed on timeout.

## Blockers resolved / safety acceptance
- Decider: base + checkpoint sha256 verified (HF LFS hash + MANIFEST.sha256); head is `safetensors`; no pickle.
- Kev revision: README's "Hub revision 9a45d25e" is the *weights* commit ("round 15"); tag `v1.0` (788ddbdd) and `main` (bf75a6a8) have byte-identical adapter/head blobs (main only adds the model card). Pinned to `v1.0`; code pinned to GitHub `kev-1.0` (6b719c3c). `head.pt` embeds `base_revision` dc7cdfe2 = our pin.
- Kev `head.pt` (pickle): opcode scan showed only OrderedDict/_rebuild_tensor_v2/FloatStorage; additionally verified loading with explicit `weights_only=True` (no fallback), and the worker forces every `torch.load` to `weights_only=True`.
- Lone-option requests are answered without calling the model (Decider schema needs ≥2); this was found in the Decider bench and fixed before the final evals (first run counted them as errors; both evals were re-run, no result selection).
- Protected-manifest refreshed for the two new backend blocks only (needs human review at merge). Full suite: 670 passed, 2 skipped; `agentos health`: 0 FAIL, 3 WARN (unchanged). No push/merge, no activation, no paid APIs, held-out file untouched.

## Recommendation / next
1. Keep `backend: null` (deterministic policy order). Do not promote any candidate.
2. If SystemOne work continues: (a) Decider-2B + explicit abstain as an *advisory/shadow* backend only, logging disagreement with the deterministic router; (b) a decision format that removes label bias (opaque aliases + description-only options, order-equivariant scoring) before re-testing — that attacks G2/G4, which no model swap fixed; (c) larger/independently labelled held-out v2 (new file; v1 stays frozen).
3. Not done / out of scope: hosted Clef-Flash reference (needs spend/egress authorisation), Open-Jev-2B reserve, Ollaya runtime.
