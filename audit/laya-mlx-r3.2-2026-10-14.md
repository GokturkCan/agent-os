# Laya-MLX on the Mac — R3.2A/R3.2B evidence (2026-10-14)

**Status recorded:** `laya-mlx` is **measured (operational benchmark only)** and **benchmark candidate**.
It is **not** a production backend, **not** the default (`systemone.backend` stays `"null"`), and
`fastgate.model` stays `null`. Decision *quality* has **not** been measured (see Findings).

## Result in one paragraph

Laya-MLX installs in an isolated runtime (906 MiB), starts in ~0.5 s, answers a routed worker-choice
question in ~18 ms p50 / ~23 ms p95, never produced a malformed reply, never returned an ineligible
option, and reproduced its own 200-decision sequence bit-for-bit across two independent processes.
But on the current question formulation its answers are driven by a fixed preference over the *label
strings*, not by the task (below), so operational readiness does not imply useful decisions.

## Environment

| | |
|---|---|
| Hardware | Apple M4, 16.0 GiB unified memory, arm64 |
| OS | macOS 27.0.1 |
| Runtime | Python 3.11.13 (isolated venv, `uv` 0.8.4), `laya-mlx` 0.4.0, `mlx` 0.32.3, device `Device(gpu, 0)` |
| Full pinned set | `state/runtime/laya-mlx/requirements.freeze.txt` (20 packages; no torch/transformers) |
| agentos commit benchmarked | `e73e287` + the benchmark harness itself (uncommitted when run: tree dirty = True) |

## Model and provenance

| | |
|---|---|
| Checkpoint | `aac6fef/laya-multilingual-mlx` @ `f2b4faf51023039425946074e2cf1361d2db11d5` (FP16, mmBERT-base, 322M parameters, 1,024-token context) |
| Weights file | `model.safetensors`, 643,835,426 bytes, SHA-256 `7fc5834af4d8fdfb268d272a9d1a66e5819a0daac98241651c4c888cc43adff1` (**verified** against the Hugging Face LFS hash) |
| Tokenizer | `tokenizer/tokenizer.json`, SHA-256 `609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f` (**verified**) |
| Upstream | `convaiinnovations/laya-multilingual` (Apache-2.0). The MLX package and weights are an **independent community port, not an official Convai release** (stated by the package itself). |
| Package | `laya-mlx` 0.4.0, Apache-2.0, pure-Python wheel, SHA-256 `f8f92dd6959ce22d7dc6c334ce68740b47aee607d1fa8271c010ce3d4f5857da` (**matches PyPI**) |
| Why this checkpoint | `docs/current-architecture.md` names the intended first checkpoint as "multilingual Laya, ~322M params, Mac mini". The repo never recorded a model id or source; these were identified from PyPI/Hugging Face metadata on 2026-10-14. |

Pre-install review of the wheel (not installed until reviewed): 4,579 lines in the top-level modules plus a small demo subpackage; no sockets/`requests`/
pickle/`trust_remote_code`; the only subprocess use is an unused Snake demo; one `HF_TOKEN` environment
read in an unused router module (hence the scrubbed worker environment); `mx.eval` hits are MLX array
evaluation. Only safe file types were downloaded (safetensors, JSON, tokenizer).

## Install performed (exact)

```bash
# isolated runtime, git-ignored (state/*), not an agentos dependency
uv venv --python 3.11 state/runtime/laya-mlx/venv
# the exact wheel that was audited and hash-checked (deps resolved from PyPI, then frozen)
uv pip install --python state/runtime/laya-mlx/venv/bin/python laya_mlx-0.4.0-py3-none-any.whl
# weights: pinned revision, safe patterns only, dedicated HF_HOME (nothing written to ~/.cache)
HF_HOME=state/runtime/laya-mlx/hf-home venv/bin/python -c "from huggingface_hub import snapshot_download; \
  snapshot_download('aac6fef/laya-multilingual-mlx', revision='f2b4faf5…', local_dir='state/runtime/laya-mlx/models/laya-multilingual-mlx', \
  allow_patterns=['model.safetensors','rl_agent_config.json','encoder/config.json','tokenizer/*','mlx_config.json',…])"
```

Nothing else was installed; no existing cache was duplicated (none existed); `~/.cache` has no
huggingface/mlx directory. At inference the worker runs **offline** (`HF_HUB_OFFLINE=1`) with a
**scrubbed environment** (no inherited tokens or API keys).

## Footprint

| | bytes |
|---|---:|
| venv (Python deps) | 272,166,808 |
| model + tokenizer | 678,239,476 |
| **total new on disk** | **950,406,284** (906 MiB) |

Disk free after install: 60 GiB. Worker RSS ≈ 0.75–1.1 GiB, inside `ram_budget_gb_for_models: 6`.

## Smoke result

`agentos systemone smoke --backend laya-mlx` → started, one `choose` request answered, parsed into a
typed `SystemOneResponse` (`escalate: false`, `reason_code: backend-choice`, confidence
`kind: raw`). Invalid output, timeout, crash, unavailable backend and ineligible options all escalate
and leave routing unchanged (`evals/test_systemone_adapter.py`, `evals/test_laya_smoke.py`).

## Benchmark

Command (run twice, as separate processes, quiet machine):

```bash
uv run agentos systemone bench --backend laya-mlx -n 200 --warmup 10 --seed 1337 --repeat 20 \
    --out audit/laya-mlx-r3.2/run{1,2}.json
```

Workload: 200 seeded synthetic worker-choice requests (compact operational state, 1–3 options).
Latency is end-to-end through the adapter (payload build, JSON over pipes, model, validation).

| Metric | Run 1 | Run 2 |
|---|---:|---:|
| Cold start: spawn → ready (model load + warm-up), s | 0.55 | 0.492 |
| Cold start: first decision incl. spawn, ms | 610.0 | 508.8 |
| Warm decision latency p50, ms | 17.885 | 18.189 |
| Warm decision latency p95, ms | 21.925 | 22.919 |
| Warm decision latency p99, ms | 23.871 | 24.628 |
| Warm decision latency min / max, ms | 11.411 / 81.401 | 14.001 / 65.264 |
| Sequential throughput, decisions/s | 55.58 | 52.08 |
| Valid-choice rate (choice ∈ eligible options) | 1.0 | 1.0 |
| Malformed-response rate | 0.0 | 0.0 |
| Escalation rate | 0.0 | 0.0 |
| Repeat consistency (20× same request → distinct answers) | 1 | 1 |
| Worker RSS min / peak sampled, MiB | 805.9 / 810.1 | 749.7 / 1101.4 |
| Raw confidence range (kind=raw) | 0.4057–1.0 | 0.4057–1.0 |
| Decision-sequence SHA-256 (200 decisions) | 8cfe3aff326c8162… | 8cfe3aff326c8162… |

Reproducible: identical decision sequence across processes; p50 within 2%, p95 within 5%. Raw
per-decision latencies are in `run1.json` / `run2.json`.

## Findings and known limitations

1. **Decision quality is unmeasured.** There is no labeled dataset, so no accuracy is claimed; the
   valid-choice rate only shows the answers were protocol-valid and policy-eligible.
2. **On this question, Laya acts on label strings, not the task.** Over the 146 multi-option
   requests of the workload: with `{claude_code, codex}` it chose `claude_code` **109/109** times
   regardless of state and of option order (swapping the order gives the same winner); with the
   3-option set it chose `deepseek_harness` 25× and `claude_code` 12×. The options are bare worker ids
   with no description, so there is little for the model to reason over. R3.2C needs richer option
   descriptions (e.g. worker roles) and a labeled set before any quality claim.
3. **Raw confidence is not calibrated.** Values span 0.4057–1.0.
   The package describes its probabilities as calibrated, but that is unverified on this workload, so
   every confidence stays `kind="raw"`.
4. **Cold start is paid per process.** There is no daemon; each short-lived `agentos` CLI process that
   selects Laya would pay ~0.5–0.6 s (plus imports) before its first decision. Long-lived callers amortize it.
5. Cold start was measured with a warm OS page cache (not a disk-cold start). Single machine, synthetic
   workload, one model, one run pair. Memory is `ps` RSS sampled every 20 decisions (run 2 sampled a
   higher peak, 1,101 MiB, than run 1, 810 MiB).
6. Independent community port of an upstream model; pinned by hash, reviewed, but not vendor-supported.
7. The benchmark harness was uncommitted when these runs were made (recorded above).
8. The recorded `command` field in `run1.json`/`run2.json` originally began with an absolute local path to the
   `agentos` executable; that prefix was removed before committing (the harness now records only `agentos …`).
   No measured value was changed (every other field is byte-identical to the original output).

## Recommendation

Operationally Laya-MLX is a sound R3.2C comparison candidate (fast, small, deterministic, fails
closed). Proceed to R3.2C **only with** a richer question formulation and a labeled evaluation set;
do not enable it as a default.
