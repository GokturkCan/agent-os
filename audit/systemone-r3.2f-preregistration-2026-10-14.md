# R3.2F pre-registration (written BEFORE any R3.2F candidate was scored on any dataset)

Scope: two additional local approaches, evaluated on the same harness as R3.2C. R3.2C evidence is CLOSED and unchanged.

## Candidates (exact pins)
| | A: Open-Jev-2B | B: lookski/openjev masked-logit |
|---|---|---|
| Weights | `ZefanCai/Open-Jev-2B` @ `0c7aa498b1627be8da4acf34c863ff0ee0a92785` (LoRA r8 + scalar head, Apache-2.0); adapter sha256 2d23935b…, head.pt 3532cd57… | none (training-free) |
| Backbone | `Qwen/Qwen3.5-2B` (post-trained, NOT the -Base used by Decider) @ `15852e8c16360a2fea060d615a32b45270f8a8fc`, shard 4,548,221,488 B | `Qwen/Qwen3-0.6B` @ `c1899de289a04d12100db370d81485cdf75e47ca`, model.safetensors 1,503,300,328 B |
| Code | `Zefan-Cai/Open-Jev` @ `bd4118882f733574a3250a4b65fe4d884130c08b` (MIT; the card's training commit 99e88110 is not in the public repo, so the loader at HEAD is used and recorded) | `lookski/openjev` @ `49eb1382c88024e0f2550005264c13847d6ec167` (MIT) |
| Runtime | torch 2.8.0 / transformers 5.10.2 / peft 0.19.1 (upstream exact pins), py3.13, venv `state/runtime/openjev2b` | torch 2.8.0 / transformers 5.10.2, py3.13, venv `state/runtime/openjev-masked` |
| Device/dtype | MPS, released bfloat16 (no fp32 upcast = no 9 GiB spike; no quantization — upstream quantization is CUDA/bitsandbytes only and changes numerics) | MPS, bfloat16 |
| Method | each `name: description` candidate scored independently (own sequence), head logit, saved temperature 1.5188 | ONE forward pass; options shown as letters A.. with description text only; softmax over letter-token logits |

Not used: lookski's `scripts/download_model.py` (defaults to a mirror endpoint); official HF only.

## Frozen adapter decisions (no tuning afterwards)
* Same payload as every R3.2C backend: `systemone_options.build()` -> `laya_worker.criteria_for` (variants `bare`, `described`, `described+abstain`; abstain text unchanged).
* Single-option requests are answered without the model (confidence 1.0, as for Decider/Kev); 0 options never reach a worker (adapter: `no-eligible-options`).
* Masked-logit: option ids are invisible to the model by design; in `bare` the id is the option text. >26 options -> upstream KeyError -> typed error -> escalation. Letter-position bias is expected and is measured by the order metrics, not corrected.
* Open-Jev-2B: no prefix cache, batch 8, max_length 4096 (input rejected, not truncated, upstream).
* Confidences are RAW (`kind="raw"`); the checkpoint's temperature is Open-Jev's own and is not presented as calibration for our task.

## Protocol
1. Smoke + contract (G1) + dev (`systemone-decisions-v1`, 66 cases) screening. Dev may be used to debug adapters only.
2. Both candidates are then run once on the frozen held-out v1 (sha256 3affe3b4…), regardless of dev outcome, unless a candidate is BLOCKED (G1 failure, or G6: RSS > 7 GiB or p95 > 1 s). No prompt/threshold tuning after seeing held-out; crash fixes only, logged.
3. **Held-out v1 is NOT pristine for this round**: it was already used for R3.2C model selection and its results were seen. This round is an explicitly additional comparison; a candidate that passes would need a fresh held-out v2 before any adoption.
4. Gates G1–G7 exactly as in Phase 2A §6 (G2 swap-all follows-label ≤ 0.60 on held-out; G3 counter-prior ≥ 0.60; G4 order-consistency ≥ 0.80; G5 ≥ label-prior(0.615) + 0.05; G6 p95 ≤ 1 s & RSS ≤ 7 GiB; G7 abstention precision ≥ 0.5). Failing G2 or G3 is NO-GO. Gate values are taken from the `described` variant (G7 from described+abstain) on held-out, dev reported alongside, as in the R3.2C closure.
5. Interpretation note fixed in advance: for the masked-logit method (id invisible) a low "follows-label" is structural, not evidence of semantic quality; it is reported but the gates are applied unchanged, and G3/G4/G5 decide.
6. Performance: existing `agentos systemone bench` (n=200, warmup 10, seed 1337); additionally for B a separate script separating prompt construction/tokenization from the model forward pass; worker RSS plus a system memory-pressure sample.
