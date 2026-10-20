# R3.2F closure — Open-Jev-2B and lookski/openjev (masked-logit, Qwen3-0.6B): five-way comparison (2026-10-14)

**Verdict: both candidates FAIL the unchanged G1–G7 gates → NO-GO preserved. Production default stays `systemone.backend: null`.**
Open-Jev-2B misses G2 and G3 only narrowly on held-out and is the strongest candidate measured so far; it is a *serious contender for a fresh validation round*, not an adoptable backend. The masked-logit method is clearly not.

Pre-registration (committed before any R3.2F score existed): `audit/systemone-r3.2f-preregistration-2026-10-14.md` (commit 304e546).
**Held-out v1 caveat:** this was an additional comparison round on a set already exposed during R3.2C selection; it is not a pristine validation of the expanded candidate search. Dev is for screening only. n=64 synthetic cases; no statistical claims.

## New candidates (exact artifacts, all hashes verified against HF/manifest)
* **Open-Jev-2B**: `ZefanCai/Open-Jev-2B`@0c7aa498 (LoRA r8 + scalar head; package manifest, 11/11 files verified) on `Qwen/Qwen3.5-2B`@15852e8c (post-trained, not -Base; shard sha aa33250c…). Loader `Zefan-Cai/Open-Jev`@bd411882 (the card's training commit 99e88110 is not in the public repo — loader at HEAD used). torch 2.8 / transformers 5.10.2 / peft 0.19.1 (upstream exact pins), MPS, released **bfloat16** (no fp32 upcast, no quantization: the upstream quantized path is CUDA/bitsandbytes and changes numerics). `head.pt` opcode scan: only OrderedDict/_rebuild_tensor_v2/FloatStorage; upstream loads with `weights_only=True`, worker forces it too. Each candidate `name: description` is scored in its own sequence (order-independent by construction; names AND descriptions visible).
* **lookski/openjev + Qwen3-0.6B**: code `lookski/openjev`@49eb1382 (MIT), model `Qwen/Qwen3-0.6B`@c1899de2 (sha f47f7117…, official HF — the repo's download script defaults to a mirror and was not used). bf16 on MPS, training-free: one forward pass, options shown as letters A.. **with description text only (option ids invisible)**, softmax over the letter-token logits. Code review: first-token ids are asserted single-token (fails loudly); >26 options → KeyError → typed error → escalation; single option rejected by `Choice.validate` (worker answers it without the model); empty sets never reach a worker; confidences are rounded raw softmax, never calibrated; positional bias is the method's main risk (confirmed below).

## Five-way table (held-out v1, `described` unless stated; dev in parentheses)
Conditions: Laya = MLX fp16 322M; Decider = MLX, LoRA merged, bf16 2B (Qwen3.5-2B-Base); Kev = MLX bf16 0.8B; Open-Jev-2B = **torch/MPS bf16 2B, independent per-option scoring (no MLX path)**; masked = torch/MPS bf16 0.6B. Rows 4–5 are the new measurements (R3.2F); rows 1–3 are the unchanged R3.2C results.

| | 1 Laya | 2 Decider-2B | 3 Kev-0.8B | **4 Open-Jev-2B** | **5 masked+Qwen3-0.6B** |
|---|---|---|---|---|---|
| acceptable (label-prior 0.615) | 0.685 (0.649) | 0.731 (0.825) | 0.661 (0.740) | **0.723 (0.870)** | 0.646 (0.617) |
| forbidden-choice rate | 0.115 | 0.061 | 0.054 | 0.092 | 0.146 |
| counter-prior acceptable | 0.542 (0.467) | 0.653 (0.956) | 0.528 (0.378) | 0.583 (0.644) | 0.583 (0.467) |
| swap-all follows-label | 0.883 | 0.830 (dev 0.50) | 0.808 | 0.638 (dev 0.297) | 0.851 (dev 0.892) |
| order-consistent | 0.623 (0.640) | 0.264 (0.500) | 0.170 (0.240) | **1.000 (1.000)** | 0.151 (0.080) |
| EN / TR acceptable | .667/.703 | .742/.719 | .667/.656 | .758/.688 | .621/.672 |
| escalate-gold correct with abstain | 1.00 | 0.357 | 0.857 | 0.857 | 0.929 |
| abstention precision / acceptable with abstain | 0.173 / – | 0.50 / 0.692 | 0.429 / 0.577 | **0.667** / 0.677 | 0.143 / 0.269 (60% of answerable escalated) |
| protocol / e2e / policy suite | 149/149, 6/6, 4/4 | 149/149, 6/6, 4/4 | 149/149, 6/6, 3-4/4 | 149/149, 6/6, 4/4 | 149/149, 6/6, 4/4 |
| warm p50 / p95 / p99 (bench) | 18 / 22 / 24 ms | 165 / 169 / 170 ms | 55 / 72 / 79 ms | 414 / 624 / 739 ms | 98 / 122 / 131 ms |
| throughput (dec/s) | 55.6 | 8.2 | 23.0 | 2.9 | 13.2 |
| cold start (spawn→ready) | 0.55 s | 5.7 s | 3.0 s | 11.5 s | 7.5 s |
| memory (worker) | 0.8 GiB RSS | 2.7–3.0 GiB RSS | 1.5 GiB RSS | **6.1 GiB footprint** (RSS 0.6 — excludes GPU) | 1.8 GiB footprint |
| runtime dir (venv+weights) | 0.9 GiB | 5.6 GiB | 3.7 GiB | 5.0 GiB | 1.9 GiB |

Eval-harness latency (richer payloads, more options): Open-Jev-2B described p95 948 ms and described+abstain p95 1,266 ms (**above 1 s**); the G6 bench payload (≤4 KiB) is 624 ms.
Method overhead (masked): prompt build + tokenize 0.8 ms of ≈105 ms per decision; the Qwen3-0.6B forward pass (≈105 ms, uncached bf16 on MPS) is the cost (`masked-overhead.json`).
System memory (`memory_pressure`): free 73% → 45% with Open-Jev-2B loaded (65% for masked); Open-Jev-2B footprint grew ≈6 MB per 10 requests over 60 (not shown to be a leak).

## Gates G1–G7, exactly as defined (held-out, with dev noted)
| Gate | Laya | Decider | Kev | **Open-Jev-2B** | **masked** |
|---|---|---|---|---|---|
| G1 protocol ≥ 0.99, no uncontained crash | pass | pass | pass | pass | pass |
| **G2** swap-all follows-label ≤ 0.60 (NO-GO if failed) | FAIL .88 | FAIL .83 | FAIL .81 | **FAIL .638** (dev .297 pass) | FAIL .85 |
| G3 counter-prior ≥ 0.60 (NO-GO if failed) | FAIL .54 | pass .65 | FAIL .53 | **FAIL .583** (dev .644) | FAIL .58 |
| **G4** order-consistency ≥ 0.80 | FAIL .62 | FAIL .26 | FAIL .17 | **pass 1.00** | FAIL .15 |
| G5 ≥ label-prior + 0.05 | pass +.070 | pass +.116 | FAIL +.046 | pass +.108 | FAIL +.031 |
| G6 p95 ≤ 1 s (bench payload) & RSS ≤ 7 GiB | pass | pass | pass | pass (624 ms; 6.14 GiB footprint, tight) | pass |
| G7 abstention precision ≥ 0.5 | FAIL .17 | pass .50 | FAIL .43 | **pass .667** | FAIL .14 |
| Overall | NO-GO | NO-GO | NO-GO | **NO-GO (G2, G3 — narrow)** | NO-GO (G2–G5, G7) |

## Findings
1. **Open-Jev-2B** is the only candidate that reads the descriptions (dev swap-all follows-label 0.30; held-out 0.64) and the only one that is order-invariant (G4 1.00 — by construction; this is the structural fix R3.2C recommended). It reaches 0.72 / 0.87 (held-out / dev) acceptable, with the best abstention precision. Its failure is two thresholds missed by 0.04 and 0.017 on 64 cases (≈2–3 decisions), while the same metrics pass on dev; with this sample size the held-out result is not decisive in either direction. Costs: 4.5 GB base download, 6.1 GiB footprint on a 16 GB Mac (system free memory 73→45%), 0.4–0.6 s per decision (≈1.3 s p95 with abstain on larger requests), 11 s cold start, no MLX path.
2. **Masked-logit** is label/position-driven (letter bias: order-consistency 0.08–0.15, first-listed-share extreme) and, with abstain exposed, escalates 60% of answerable held-out cases. The method overhead is negligible; the weakness is the 0.6B model plus the letter-choice format. Not a contender.
3. Neither new candidate changes the R3.2C conclusion that no candidate qualifies; Open-Jev-2B changes the *direction*: independent per-option scoring addresses G2/G4 where Laya, Decider and Kev (shared-context pointer heads) did not.
4. Winner is not selected on headline accuracy: Decider (0.731) and Open-Jev-2B (0.723) are statistically indistinguishable here; Open-Jev-2B differs on the gate-relevant properties (order, description use).

## Safety acceptance / constraints honoured
All downloads exact-pinned, offline thereafter, hash-verified; `torch.load` restricted to `weights_only=True`; isolated venvs/caches under git-ignored `state/runtime/`; no global installs; workers run with the adapter's scrubbed env; failures escalate; no push/merge/activation/paid API/training; frozen held-out file and all R3.2C evidence untouched. Protected `config/systemone.yaml` gained two blocks and `evals/protected-manifest.json` was refreshed — **this does not constitute human approval; both need human review before merge.**

## Recommendation
1. Keep `backend: null`. Do not promote any of the five.
2. Open-Jev-2B warrants a **fresh, independently labelled held-out v2** (new file, larger, more cases per family, authored before scoring) — specifically re-testing G2/G3 — plus a memory/latency decision for the 16 GB host (6.1 GiB footprint; consider only as an on-demand/shadow backend). If it passes on v2, then a shadow-mode trial with logging against the deterministic router. If v2 repeats the narrow miss, preserve NO-GO.
3. Do not pursue masked-logit/letter-choice further for this task.
4. Open items: Open-Jev's own evaluation is on its synthetic mixture (not our task); the card's training commit is not public; Qwen3.5-2B (post-trained) differs from the Decider's -Base.
