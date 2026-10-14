# R3.2C Phase 2A — FastGate Candidate Verification & Benchmark Freeze

Date: 2026-10-14 (all source access dates below). Branch `feature/run3-local-intelligence`, baseline `4879c1f`.
Scope: research and evaluation design only. **Nothing was installed, downloaded (beyond JSON/README/doc text), benchmarked, or spent.
No repo file other than this report was created or modified. No commit.**

Evidence labels: **VERIFIED** (read from a primary source today) · **DOCUMENTED** (stated by the maintainer, not tested by us) ·
**ESTIMATED** (our arithmetic/inference) · **UNKNOWN** · **NOT SUITABLE**.

---

## 1. Executive summary

* Phase 1 showed Laya-MLX is fast (p50 ≈ 18 ms, 906 MiB footprint, 100 % protocol-valid) but does not use option descriptions
  (swap probe: 94.6 % of decisions follow the label; label-prior baseline 0.714 beats Laya-described 0.649). The open question for FastGate
  is whether a model with a **decoder torso + pointer head** (reads relational text) fixes that at acceptable local cost.
* Names in the brief resolve to real, primary-source-verifiable artifacts, with several look-alikes that must not be confused (§3, §9).
  The name **“Decider”** is ambiguous: *Strands Decider* (AWS/Strands Labs, verified) ≠ *“Mapika’s decider”* listed inside Ollaya (different author, not verified).
* **Recommendation: install at most two, in sequence, in an isolated venv — 
  (1) Strands Decider 2B `v1-2610` (primary), (2) Kev-0.8B `v1.0` (lightweight arm).** Kev-4B/9B, Clef (27B), Clef-Flash (9B) do not fit a 16 GB Mac
  as documented (Kev-4B: documented for 32 GB; Clef-Flash: 17.8 GiB bf16).
* **Clef-Flash is kept as a hosted quality *reference* only** (Workers AI, $0.038 / M input tokens, output free). It is not a Mac candidate and it needs
  separate explicit authorization (API spend + sending held-out text to a third party). It is NOT counted in the two.
* vLLM-Jev (serving runtime) and Naive-N0.5-Flash (309B-MoE, future teacher) are kept out of the shortlist (§9).
* **Phase 2B go/no-go: GO (conditional)** for Decider-2B first; Kev-0.8B only after the Decider smoke gate passes. Estimated Phase 2B budget ≈ 8–10 GiB disk, ≈ 2–4 GiB RAM peak per candidate, < 1 engineer-day compute (§10).
* Biggest risks: MLX path for Decider requires a **git install** (PyPI 0.1.0 has no `mlx` extra); heavy torch/transformers>=5.15 dependency tree;
  Kev `head.pt` is a pickle; Kev Hub `v1.0` tag SHA disagrees with the README’s “revision” (§11); Turkish quality of every candidate is UNKNOWN.

---

## 2. Verified candidate table

| ID | Candidate | Checkpoint / revision (pinned) | Params | Weights on disk | Code / weights license | Local Mac 16 GB | Status |
|---|---|---|---|---|---|---|---|
| A | **Strands Decider 2B v1** | `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` @ `216d1ccb46a9e9b036eb9187b248db98480f77d4` (no tags on repo) | ≈1.9–2.3 B (Qwen3.5-2B-Base torso 2,274,069,824 + pointer head (head.safetensors 12.6 MB) + **r48** LoRA) | LoRA 192.5 MiB + head 12.0 MiB + base 4,337.5 MiB (bf16) ≈ **4.5 GiB** | Apache-2.0 / Apache-2.0 (card+LICENSE; base Qwen3.5 Apache-2.0) | Documented MLX (`--device mlx`), MPS, CPU | **SHORTLIST #1** |
| A′ | Decider 2B v19 | `…-2B-hobson-v19` @ `bb282d786bc251fd4e3068de3ada9ddbb38127cd` | same | LoRA 64 MiB + head 4 MiB + base | Apache-2.0 | Only variant with published Mac numbers (M3 Pro, M4 Pro) | Fallback / sanity ref |
| A″ | Decider Gemma-4 E2B/E4B/12B/26B | `…-E2B-gemma4-v1-2610` etc. | 2–26 B | E2B: LoRA 276 MiB + base | Apache-2.0 (Gemma 4 base Apache-2.0 per README) | E2B: “about 9 GB GPU memory bf16” | Not shortlisted |
| B | **Kev-0.8B** | `jaredpalmer/kev-0.8b`, tag `v1.0` → `788ddbdd65…` (main = `bf75a6a8848ea6960ff2ed108d9ed44c2941174f`) | 0.87 B base + r16 LoRA | adapter 41.3 MiB + head 2.0 MiB + base 1,666 MiB ≈ **1.7 GiB** | Apache-2.0 / Apache-2.0 | “Any Apple Silicon Mac; measured to 65 k tokens” (DOCUMENTED) | **SHORTLIST #2** |
| B′ | Kev-4B | `jaredpalmer/kev-4b` tag `v1.0` → `591dcb5bd6…` | 4.66 B base | adapter 124 MiB + base 8.7 GiB ≈ 8.9 GiB | Apache-2.0 | README: “32 GB Mac” (measured), 13.0 GB peak at 65 k tokens | NOT SUITABLE for 16 GB |
| B″ | Kev-9B / Kev-27B | `kev-9b`, `kev-27b` | 9 / 27 B | ≥17 GiB / 51 GB | Apache-2.0 | 32 GB+ / 96–128 GB | NOT SUITABLE |
| C1 | **Clef-Flash** (9B) | `Cloudflare/clef-flash` @ `8b2e5fd17c09fd49bc2880b805d5323ec7ff4ff3` | 9,409,813,744 | 17.77 GiB bf16 (+ joint_head 232 MiB) | Apache-2.0 / Apache-2.0 | Does not fit 16 GB bf16 | **Hosted reference only** |
| C2 | **Clef** (27B) | `Cloudflare/clef` @ `0b331204bb13fbd2ca93a64df1956f5b55478ce5` | 27,356,728,560 | 51.21 GiB | Apache-2.0 | NOT SUITABLE | Hosted reference (optional) |
| C3 | Clef-Omni (30B-A3B) | `Cloudflare/clef-omni` @ `0db1cd2607…` | 35.3 B | 65.9 GiB | Apache-2.0 | NOT SUITABLE | Found incidentally (in pricing + HF); not in the blog post |
| C4 | Jev (TypeSafe) | hosted API only | n/a | n/a | proprietary | cloud mandatory | NOT SUITABLE (not local) |
| C5 | OpenJev family | several unrelated repos (§9) | – | – | MIT mostly | – | UNRESOLVED / NOT SUITABLE as a “model” |
| D | `FluidInference/clef-text-0.6b` | @ `9eeb9cba87…` (third party) | 0.70 B | 1.31 GiB | Apache-2.0 | torch CPU/MPS; CoreML build exists | Not shortlisted (§9) |
| R | Ollaya | `ollaya-dev/ollaya` v0.13.0 | n/a | runtime daemon | Apache-2.0 | ONNX CPU / llama.cpp Metal | Runtime, not a model — NOT proposed |

Architecture facts (VERIFIED from READMEs/cards): Decider and Kev both use a frozen-ish Qwen3.5 decoder torso + a LoRA adapter (Kev-0.8B: r16/α32; Decider v1: **r48/α96** — see A.7; the README’s “rank-16” describes v19/v21) + a pointer head that compares
the hidden state at an `<answer>`/`<decide>` marker with each option’s last token; no text generation; option count not baked into weights;
question kinds `noul` (yes/no), `choice`, `score`. Clef/Clef-Flash use a *joint* schema head over all questions (rank-256 adapters on Qwen3.8-27B / Qwen3.5-9B per the blog) and also take images/video.

Contextual candidate selection (the property FastGate needs): **yes for A, B, C** — each choice carries an instruction and per-option
description (`criteria`), which the model reads (DOCUMENTED; whether it is *used* well is exactly what Phase 2B measures — Laya also “accepts” descriptions).

Output types: probability per option per question; confidence is a *calibrated-by-temperature* probability (Decider: calibrated on held-out; Kev: single fitted temperature; Clef: trained with Brier loss).
**In Agent OS these remain `kind="raw"`** until R3.3; no candidate output may be marked calibrated here.

Context limits: Decider window 3072–4096 tokens (v19 preregistered 3072; saved 4096) (DOCUMENTED); Kev validated 8,192, server accepts 65,536 (DOCUMENTED); Clef 65,536 (VERIFIED, Cloudflare docs). Agent OS payload cap (`MAX_PAYLOAD_BYTES=4096`) is far below all of these.

---

## 3. Source / provenance table (accessed 2026-10-14)

| Fact | Source (URL) | Type | Notes |
|---|---|---|---|
| Decider repo, license, push date, no releases | https://api.github.com/repos/strands-labs/strands-decider | GitHub API | Org `strands-labs`, Apache-2.0, created 2026-09-29, pushed 2026-10-13, 612★, no GH releases, HEAD `8b6faa5530…` |
| Decider README / docs | https://github.com/strands-labs/strands-decider (README, `docs/inference.md`) | maintainer | MLX, MPS, naming, Mac latency |
| Decider PyPI | https://pypi.org/pypi/strands-decider/json | PyPI | 0.1.0 (2026-10-01), whl 147,704 B, sdist 33.3 MB, needs `torch>=2.7`, `transformers>=5.15,<6`, `peft>=0.21`, no `mlx` extra |
| Decider v1 checkpoint | https://huggingface.co/api/models/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610?blobs=true | HF API | sha `216d1ccb…`, apache-2.0, head 12,605,928 B (sha256 `ace56742…`), LoRA 201,878,888 B (sha256 `ae1d0cd1…`); mirrored at `amazon/…` (sha `974685f9…`, different) |
| Decider v19 checkpoint | https://huggingface.co/api/models/StrandsAgents/strands-decider-2B-hobson-v19?blobs=true | HF API | sha `bb282d78…`, 37 files, 92 MB |
| Qwen3.5-2B-Base | https://huggingface.co/api/models/Qwen/Qwen3.5-2B-Base?blobs=true | HF API | sha `b1485b2f…`, apache-2.0, 2,274,069,824 params, 4,337.5 MiB |
| Kev repo | https://api.github.com/repos/jaredpalmer/kev | GitHub API | User `jaredpalmer`, Apache-2.0, created 2026-09-17, pushed 2026-10-13, 9,084★, releases `kev-1.0`, `kev-family`, `v0.1.0`, HEAD `0a6d3fafee…` |
| Kev README | https://github.com/jaredpalmer/kev | maintainer | Models table, MLX, API, limitations |
| Kev-0.8B / 4B / 9B | https://huggingface.co/api/models/jaredpalmer/kev-{0.8b,4b,9b}?blobs=true | HF API | apache-2.0; `head.pt` (pickle) + adapter safetensors; Kev-0.8B adapter sha256 `9b908623…`, head sha256 `f400bd12…` |
| Kev HF tags | https://huggingface.co/api/models/jaredpalmer/kev-0.8b/refs | HF API | `v1.0 → 788ddbdd65`, main `bf75a6a884` |
| Kev GH tag | https://api.github.com/repos/jaredpalmer/kev/git/ref/tags/kev-1.0 | GitHub API | → `6b719c3c3f36…` |
| Clef announcement | https://blog.cloudflare.com/clef-decision-models/ | vendor blog (2026-10-01) | Qwen3.8-27B / Qwen3.5-9B, rank-256, 64 k context, Jev-API compatible, hosted on Workers AI, Apache-2.0 on HF, no-store policy for requests |
| Clef / Clef-Flash cards | https://huggingface.co/api/models/Cloudflare/clef(-flash)?blobs=true and `/raw/main/README.md` | HF API | apache-2.0; tested with torch 2.11, transformers 5.10.2, one H200; SGLang serving; no Mac/MLX statement |
| Workers AI model page | https://developers.cloudflare.com/workers-ai/models/clef/ | vendor docs | 65,536 context, $0.24/M input (27B), output not billed, images ≤4, 13 MiB body |
| Workers AI pricing | https://developers.cloudflare.com/workers-ai/platform/pricing/ | vendor docs | `clef` $0.240/M in (21,818 neurons/M); `clef-flash` **$0.038/M in** (3,455 neurons/M); `clef-omni` $0.150/M in; free-tier allowance NOT checked |
| Clef-Omni | https://huggingface.co/api/models/Cloudflare/clef-omni?blobs=true | HF API | 65.9 GiB, base Qwen3-Omni-30B-A3B-Instruct |
| Third-party Clef ports | HF search “clef”: `ggml-org/Clef-Flash-GGUF`, `bartowski/Cloudflare_clef-flash-GGUF`, `Jundot/clef-flash-oQ4e` (5.86 GiB), `FluidInference/clef-text-0.6b(-coreml)` | HF API | Third-party; none tested; GGUF/quant outputs of a *joint head* model unverified |
| OpenJev & friends | https://api.github.com/search/repositories?q=OpenJev (also `ollaya`, `jevlike`, `vllm-jev`, `naive-n0.5`) | GitHub search | See §9 |
| Ollaya | https://api.github.com/repos/ollaya-dev/ollaya + README | GitHub | Apache-2.0, Rust, v0.13.0 (2026-10-13), lists decider/kev/clef/laya as served models |
| Laya baseline | repo `audit/laya-mlx-r3.2/*`, `audit/systemone-eval-r3.2c/*`, `audit/*phase1*` | local, committed | §5 |

Date caveat: the blog and models are < 6 weeks old. Everything here is a point-in-time snapshot; Phase 2B must re-pin and re-verify hashes at download time.

---

## 4. Mac M4 feasibility matrix (16 GB RAM, ~60 GiB free disk, Python 3.11/3.13/3.14 present, no Python 3.12)

Disk free VERIFIED (`df`: 228 GiB total, 60 GiB avail). No `~/.cache/huggingface` exists (VERIFIED), so a Phase 2B download would be the first and would be inside a repo-local cache we choose.

| Candidate | Download | RAM (resident) | Runtime path | Cold start | Offline | Cloud key | Verdict |
|---|---|---|---|---|---|---|---|
| Decider 2B v1 (bf16, MLX) | ≈4.5 GiB (+ venv ≈ 2–4 GiB ESTIMATED: torch, transformers 5.x, peft, mlx-lm) | ≈ 5–6 GiB (ESTIMATED: 4.3 GiB weights + KV/activations; docs cap MLX cache 1 GiB) | `strands-decider` from git clone with `[mlx]` extra, `--device mlx`; fallback MPS | UNKNOWN (adapter merge into bf16 at load); ESTIMATE 3–10 s | yes after download (HF cache) | no | **FEASIBLE** |
| Kev-0.8B (bf16, MLX) | ≈1.7 GiB (+ venv ≈ 1–2 GiB: mlx-lm, torch, fastapi) | ≈ 2.5–3.5 GiB (ESTIMATED) | Kev serve (uv, py 3.13) or in-process `DecisionModel` | UNKNOWN; ESTIMATE 2–6 s | yes | no (TypeSafe SDK used with `api_key="local"`) | **FEASIBLE** |
| Kev-4B | ≈8.9 GiB | README: adapter merge “briefly holds a second copy” → ESTIMATED transient up to ≈ 2× 8.4 GiB; 13.0 GB peak at 65 k | MLX | – | – | – | **NOT SUITABLE on 16 GB** (documented for 32 GB) |
| Clef-Flash 9B bf16 | 17.77 GiB | > 17 GiB | torch/transformers CUDA-tested; no MLX documented | – | – | – | **NOT SUITABLE locally** (would swap/OOM). Third-party 5.86 GiB quant exists, unvalidated |
| Clef 27B / Omni | 51 / 66 GiB | – | – | – | – | – | NOT SUITABLE |
| clef-text-0.6b | 1.31 GiB | ≈ 2 GiB (ESTIMATED) | torch CPU/MPS (+ CoreML build 1.32 GiB) | – | yes | no | feasible but third-party — deferred |
| Laya-MLX (baseline, installed) | 906 MiB | 750–1,101 MiB (VERIFIED) | existing runtime | 0.49–0.55 s | yes | no | reference |

Latency expectation (all ESTIMATED from maintainers’ numbers, different Macs): Decider v19, ~222 input tokens: 113 ms on M4 Pro MLX (DOCUMENTED, one question); 153 ms warm median on M3 Pro MPS.
Kev-0.8B: 149 ms for 5 questions, ~270 tokens, M5 (DOCUMENTED). On an M4 with 16 GB expect **≈ 100–400 ms per request**, i.e. **6–20× slower than Laya (≈18 ms)**.
For per-decision routing this is still sub-second, but it must be reported as a cost, not hidden.

Other feasibility notes:
* Memory-pressure measurement caveat from Phase 1: `vm_stat` (≈3.3 GiB reclaimable) and `memory_pressure` (41 % free) disagree in method; Phase 2B should record both and run candidates one at a time, never alongside another model.
* Python: Kev requires 3.12/3.13 (README) → Homebrew 3.13.11 exists. Decider PyPI needs ≥3.10 (docs use 3.12) → 3.11.13/3.13 exist. Neither needs a system Python change; each needs its own venv under `state/runtime/<name>/` — consistent with the Laya layout and with “no system-wide installs”.
* Network at install time is required once; runtime must be offline (`HF_HUB_OFFLINE=1`) — already the adapter’s scrubbed-env convention.

---

## 5. Laya baseline (all VERIFIED from committed evidence)

Operational (R3.2B, `audit/laya-mlx-r3.2/run{1,2}.json`): footprint 950,406,284 B (906.4 MiB; venv 272,166,808 + models 678,239,476); cold spawn→ready 0.55 / 0.49 s; first decision incl. spawn 610 / 509 ms; warm p50 17.9 / 18.2 ms, p95 21.9 / 22.9, p99 23.9 / 24.6; throughput 55.6 / 52.1 dec/s; RSS min 806 / 750 MiB, sampled peak 810 / 1,101 MiB (the “~1.1 GiB” occurs only in run 2); valid 1.0, malformed 0; decision-sequence hash `8cfe3aff326c8162…`; laya_mlx 0.4.0, mlx 0.32.3, Python 3.11.13.

Quality (R3.2C Phase 1, `systemone-decisions-v1.yaml`, 66 cases): acceptable 0.539 bare / 0.649 described / 0.305 described+abstain; forbidden 0.234 / 0.149 / 0.039; counter-prior 0.289 / 0.467 / 0.378; escalation-gold correct 0 / 0 / 0.75; order-consistent 0.86 / 0.64 / 0.02; swap probe (n=74) follows-label 0.946; abstention precision 0.133; layer-3 12/12.
Baselines: first/last 0.558, label-prior **0.714** (counter-prior 0.022), random 0.552.
**Pass bar for any candidate against Laya** is therefore not “beats Laya” but “beats label-prior on counter-prior cases *and* on the swap probe” (§6).

---

## 6. Frozen evaluation methodology (to be applied unchanged to every candidate)

Three layers stay separate and no single headline score is produced:

1. **Decision quality** (semantic): `agentos systemone-eval` on the dev set (below), variants *bare / described / described+abstain*; metrics = acceptable, forbidden, counter-prior, escalation-gold correct, order-consistency, description-swap follows-label, abstention precision/recall, plus baselines (first, last, label-prior, random). Report each with n and a Wilson 95 % interval; differences < 10 percentage points on n < 100 are labelled unresolved.
2. **Adapter / protocol compliance**: valid-reply rate, malformed rate, oversize/timeout/kill behaviour, closed escalation vocabulary, scrubbed env, offline operation (network sandbox/denied socket), decision-sequence hash reproducibility across 2 runs, `kind` always `"raw"`.
3. **End-to-end policy-valid routing**: the 12 e2e cases through `system_one()` + router; a backend answer outside `eligible_options` must never be executed (existing guarantee); failures → escalation.

Operational metrics (separate table): download size, venv size, cold start, first-decision latency, warm p50/p95/p99, throughput, RSS/peak, 2 runs, memory pressure.

**Frozen rules (set now, before any candidate runs):**
* Dev set = `evals/data/systemone-decisions-v1.yaml` (sha256 `30e211a6ea922d6ad0ae7f1a5a65a5719a8c213efb8168f48fc991d4e7412396`), unmodified. Its limits stay disclosed: only 66 cases, 12 e2e; correlated option-order variants (n_eff is lower than n); synthetic; label-prior skew (a trivial prior scores 0.714); intent labels are design intent, not measured performance; `need` is not produced by the router; cap-005 gold correction disclosed via `revision_log`. Dev results may be used for debugging adapters, never to claim generalization.
* Held-out set (§7) is used **once per candidate**, after adapter code and prompt template are frozen; no candidate-specific prompt tuning, no per-candidate threshold, no temperature changes, no re-runs after seeing held-out results except for crash fixes (logged).
* Same payload for every candidate: output of `systemone_options.build()` (roles, access, cost, locality, latency, interactive, missing) rendered by a single shared, candidate-agnostic template; Laya’s template is unchanged.
* No confidence-based decisions: raw probabilities are logged (`kind="raw"`), abstain/escalate only via the explicit option or protocol failure.
* Seeds/ordering: fixed list of 3 option-order permutations per case (identity, reverse, one fixed shuffle).
* Pre-registered success gates for Phase 2B (applied to held-out + dev, per candidate):
  G1 protocol: valid ≥ 0.99, zero uncontained crash. G2 swap probe: follows-label ≤ 0.60 (Laya 0.946). G3 counter-prior acceptable ≥ 0.60 in *described* (label prior 0.022, Laya 0.467). G4 order-consistency ≥ 0.80 in *described*. G5 acceptable(described) − label-prior baseline ≥ +0.05 on held-out. G6 p95 latency ≤ 1.0 s warm on the M4 at ≤ 4 KiB payload; peak RSS ≤ 7 GiB. G7 abstention precision ≥ 0.5 if abstain is exposed. Failing G2 or G3 is a NO-GO regardless of other scores.
* Hosted Clef-Flash reference (if authorised) is run with the same frozen files and reported in its own column, flagged “cloud, not a deployable candidate”.

---

## 7. Held-out dataset proposal

* Name `evals/data/systemone-heldout-v1.yaml` (+ a manifest hash). Created **in Phase 2B step 1 as a new file**, added to the protected manifest only after review; never touches the v1 dev file or gold labels.
* Size: ≈ 120 base cases → ≈ 360 scored instances after 3 option-order permutations (permutations are reported as one case with consistency, not as independent samples). ≥ 40 % of base cases Turkish; the rest English; ≥ 10 % mixed-language.
* Case families (min counts): worker selection by role (20); resource constraints (cost/latency/locality/access) (16); capability requirements with `missing` set (16); reviewer independence (the producing worker excluded) (12); cost vs locality trade-offs (10); abstention/escalation (insufficient info, conflicting requirements, no eligible option) (16); ambiguous task, **equally acceptable** options (10); description-swap counterfactuals (paired, 12 pairs); distractor options with similar names but opposite roles (8).
* Construction: scenarios written from `config/workers.yaml` facts and the capability registry, but **with worker ids/labels randomised per case** (aliasing) so label-string preference is detectable; gold stored as an acceptable set plus a forbidden set plus escalate-gold flag; each case carries rationale.
* Independence: author ≠ reviewer. A second reviewer (human, or a model *not under evaluation* and not Laya/Decider/Kev/Clef) labels blind; disagreements are resolved by the human owner; inter-annotator agreement is reported. Cases the reviewer calls ambiguous are moved to the “equally acceptable” family rather than deleted.
* Freeze: sha256 recorded in the report *before* any candidate sees it; any later edit creates `v2` and invalidates earlier results. Held-out text is synthetic and contains no secrets or real user data.
* Contamination note: Decider/Kev/Clef train on public datasets; our cases are new, but the set must never be posted or fed to a hosted model as training data. If hosted Clef is used, the cases leave the machine (Cloudflare states no-store/no-train — DOCUMENTED, not verified) — needs separate authorization.

---

## 8. Shortlist (maximum two)

### #1 Strands Decider 2B v1-2610
* Exact artifact: HF `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` @ `216d1ccb46a9e9b036eb9187b248db98480f77d4`; base `Qwen/Qwen3.5-2B-Base` @ `b1485b2fa6dfa1287294f269f5fb618e03d52d7c`; code `strands-labs/strands-decider` @ `8b6faa553038a59e73fa7f16c4081f8ceb21d27e` (git install, because PyPI 0.1.0 `strands-decider` lacks the `mlx` extra; do **not** use PyPI for the MLX path). Fallback pin: v19 `bb282d78…` (only version with published Mac measurements).
* Why: decoder + pointer head reads option text; no label slot baked in (README: “nothing can learn the first option is usually right”); safetensors head (not a pickle); org-backed repo; JevBench 180/231 (0.779), Brier 0.280, ECE 0.072 (DOCUMENTED, maintainer-run); MLX path measured on M4 Pro with answers matching fp32 (113 ms @ 222 tokens, v19).
* Limits: English-centric training data (Turkish UNKNOWN); window ≈ 3–4 k tokens; v1 Mac numbers not published (v19 only); MLX engine pins an mlx-lm minor version; “evaluations run one at a time” race in engine (#9); README Security section empty; 34 open issues; sub-2-month-old project; Gemma/Qwen base licences must be re-confirmed at download.
* Runtime / integration: new `systemone_workers/decider_worker.py` mirroring `laya_worker.py` (JSON-lines protocol v1: `choice` question with `criteria` = option_info); new backend block `decider-mlx` in `config/systemone.yaml` (protected, review required); venv `state/runtime/decider-mlx/`; no change to `systemone.py` contract; default stays `systemone.backend: null`.
* Download ≈ 4.5 GiB model + ≈ 2–4 GiB venv (ESTIMATED); RAM ≈ 5–6 GiB peak (ESTIMATED).
* Pre-install verification (read-only, before any download): re-fetch HF sha and per-file LFS sha256 and compare with §3; confirm `LICENSE.md` in repo; read `MANIFEST.sha256` in the model repo; resolve pinned `mlx-lm` minor and pip-resolve the dependency set in a dry run (`uv pip install --dry-run`) to list every wheel and its hash; check `git clone` at the pinned SHA only.
* Go / no-go: GO if the pinned hashes match, dry-run adds ≤ 4 GiB and no native build step is needed, and a 20-case smoke (offline, no network) returns valid replies with p95 ≤ 1 s and RSS ≤ 7 GiB. NO-GO on hash mismatch, post-install network use at runtime, or any need for system-level changes.

### #2 Kev-0.8B (v1.0)
* Exact artifact: HF `jaredpalmer/kev-0.8b` tag `v1.0` (→ `788ddbdd65…`; confirm full SHA at download) with base `Qwen/Qwen3.5-0.8B-Base` @ `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68`; code `jaredpalmer/kev` @ GitHub tag `kev-1.0` = `6b719c3c3f367295f6ef336f4f751cf5ff970abc` (main is `0a6d3fafee…`; pin the tag, not main). **Not** `ayan4m1/kev-4b-merged` (third-party merge) and **not** OpenRouter `jaredpalmer/kev-4b` (hosted route).
* Why: smallest decoder+pointer model documented for “any Apple Silicon Mac”; tests whether description-reading survives at 0.8 B (size-floor arm); same API as Jev/TypeSafe; a different author/recipe than Decider, so the comparison is not just a size sweep.
* Limits: held-out Decision Index 23.3 and new-source accuracy 0.648 (DOCUMENTED) — clearly weaker than 4B/9B; `head.pt` is a PyTorch pickle (load only with `torch.load(weights_only=True)` or convert in a sandbox — must be checked before install); “changing option order can change an answer”; validated 8 k tokens; Python 3.12/3.13 only; uv sync pulls a large serve extra (FastAPI, Modal tooling?) — UNKNOWN until dry run; the README’s “Hub revision 9a45d25e” does not equal the HF `v1.0` tag SHA (§11).
* Integration: in-process library path preferred over the HTTP server (avoids a listening socket and the TypeSafe SDK); worker `kev_worker.py` speaking the same protocol v1; backend block `kev-mlx`; venv `state/runtime/kev-mlx/` on Python 3.13.
* Download ≈ 1.7 GiB model + ≈ 1–3 GiB venv (ESTIMATED); RAM ≈ 2.5–3.5 GiB (ESTIMATED).
* Pre-install verification: verify tag→sha; compare LFS sha256 (adapter `9b908623…`, head `f400bd12…`, base from Qwen API); inspect `head.pt` with `picklescan`-style static check or `torch.load(weights_only=True)` in an isolated process; dry-run resolve of the `serve` extra; read `provenance.json`/`result.json` shipped in the repo; check the GitHub release `kev-1.0` SHA-256 list vs Hub files.
* Go / no-go: proceed only **after** the Decider smoke gate and only if the pickle check passes and the dry run stays under ≈ 3 GiB; NO-GO if the Hub tag cannot be reconciled with the GitHub release checksums.

### Not in the two, but part of the review
* **Clef-Flash (hosted reference).** Strongest documented decision quality we can reach under the constraints: blog table shows Clef-Flash ≥ Jev on BFCL, API-Bank, Home appliances; below Jev on When2Call; Decision-Index figures are vendor-published. Pricing VERIFIED: $0.038 / M input tokens, no output charge; Clef 27B $0.24 / M. A full run of ≈ 400 instances × 3 variants × ~700 tokens ≈ 0.84 M tokens ≈ **$0.03 (Flash) / $0.20 (Clef)** (ESTIMATED; free-tier not checked). Requires: Cloudflare account/token (none provisioned — UNKNOWN), explicit user authorization for spend and for sending synthetic held-out text off-device. Treated as an *upper reference column* so that a local candidate’s gap to “what a 9B joint-head model achieves” can be read, not as a FastGate candidate.
* **No install recommendation for anything else.**

---

## 9. Rejected / unresolved candidates

| Candidate | Status | Reason |
|---|---|---|
| Jev (TypeSafe) | NOT SUITABLE | Proprietary hosted API; cloud mandatory; also OpenRouter `typesafe/jev-1.13` is a hosted route. Used only as a comparison number in vendor tables. |
| OpenJev — `SiliconLabAI/OpenJev` (176★, MIT), `TheoLeeCJ/SemIf-OpenJev` (4,813★, MIT, “Independent; not affiliated with Jev”), `GPT-AGI/OpenJev`, `ekzhang/openjev-sglang` (archived), `razorback16/openjev` (DiffusionGemma server), `Heman10x-NGU/openJev-verdict-2.0` (151 M non-autoregressive; license NOASSERTION; benchmark claims unverified) | UNRESOLVED / NOT SUITABLE | “OpenJev” is a *name shared by at least six unrelated repos*; no canonical upstream, no single checkpoint. The best-known ones are a method (chat model + per-option scoring), not a trained decision model. Not downloaded, not ranked. |
| Jevlike (`vinnylarouge/jevlike`, `olanotolu/jevbetter`, …) | UNRESOLVED | Hobby repos, one-day-old pushes, no verified checkpoints. |
| “Decider” by Mapika (listed in Ollaya as `decider`, 0.8B/2B/4B/2b-vision) | UNRESOLVED | Different from the Strands Decider (author differs); only seen in a third-party README; not verified at source. Not to be confused with Strands. |
| Ollaya (daemon) | NOT PROPOSED | A new runtime/daemon (Rust, ONNX Runtime, llama.cpp). It would add a second runtime and a listening port (`localhost:11435`); violates “no competing orchestrators / no new global runtime”. Useful only as a *source of cross-model numbers* (it publishes its own results at ollaya.dev/results — not audited here). |
| Kev-4B / 9B / 27B | NOT SUITABLE | 4B documented for 32 GB; adapter merge needs a transient second copy; 9B/27B far larger. |
| Clef (27B), Clef-Omni (30B-A3B) | NOT SUITABLE locally | 51 GiB / 66 GiB. Hosted reference possible (27B $0.24/M). |
| Clef-Flash locally | NOT SUITABLE | 17.8 GiB bf16 > 16 GB RAM. Third-party quant (`Jundot/clef-flash-oQ4e`, 5.86 GiB) and GGUF ports (`ggml-org`, `bartowski`) exist but whether a *joint-head* model survives quantisation/GGUF conversion with identical probabilities is UNKNOWN and would change the model under test. |
| `FluidInference/clef-text-0.6b` (+ CoreML) | Deferred (candidate D) | Credible small option (0.70 B, 1.31 GiB, Apache-2.0, built on Cloudflare’s own module): author-reported 79.1 vs 88.2 (Clef-Flash) on 5,124 held-out questions; distilled from Clef-Flash on 12 public datasets — it is third-party, trained for 2 epochs on 24 k records on an M5 Pro, with no calibration or option-order claims; reasoning tasks drop sharply (ARC-Challenge 60.7 vs 97.3). Technically interesting, but it adds a third unvetted author. Revisit only if both shortlisted candidates fail G6 (latency/memory) but pass G2–G4. |
| Laya typed-decisions (same family) | Not tested | Phase 1 shows the architecture limit, not the checkpoint; a “typed-decisions” fine-tune might help but is outside this review’s evidence. |
| vLLM-Jev (`mode-io/vllm-jev`, Apache-2.0, 524★, pushed 2026-10-12) | SEPARATE — serving runtime | A native vLLM serving layer for Jev-style models; not a model. CUDA-oriented; no Mac path verified. Out of scope for the Mac FastGate. |
| Naive-N0.5-Flash (`NaiveAI/Naive-N0.5-Flash`, MIT, 309 B MoE / 15.5 B active) | SEPARATE — future teacher candidate | Repo describes a coding/agent LLM, not a decision model; only relevant as a possible labeller/teacher for dataset construction in a later phase. Not evaluated; far too large for the Mac. |
| Qwen / Bonsai / MSI integration | EXCLUDED by brief | – |

---

## 10. Phase 2B step-by-step plan (requires explicit authorization; none of this has been started)

0. Authorization gates: (a) install of Decider into `state/runtime/decider-mlx/`; (b) separately, Kev-0.8B; (c) separately, any hosted Clef call (spend + data egress).
1. Build and freeze the held-out set (§7); record sha256; protected-manifest update through `agentos manifest --write` after review; no model involved.
2. Pre-install verification (read-only) for Decider per §8; record outputs in `audit/`.
3. Install Decider in an isolated venv (Python 3.11 or 3.13 via existing interpreters, `uv`, hash-pinned); pre-fetch pinned weights into a repo-local HF cache; confirm `HF_HUB_OFFLINE=1`; measure footprint (venv + models).
4. Implement `decider_worker.py` + `decider-mlx` backend definition (reviewed, protected files); default `backend: null` unchanged; unit tests via `uv run pytest`.
5. 20-case smoke → go/no-go gate (G1, G6) → stop if failed.
6. Operational benchmark (2 runs: cold, warm p50/p95/p99, throughput, RSS, memory pressure) with the existing `systemone_bench` conventions.
7. Dev-set evaluation (all 3 variants, baselines, swap probe, permutations) → `audit/systemone-eval-r3.2c/decider-mlx.json`.
8. Held-out evaluation (once) → gates G1–G7 → report with intervals.
9. Repeat 2–8 for Kev-0.8B only if (5) passed for Decider (or Decider failed with a documented, non-fundamental cause).
10. Optional: hosted Clef-Flash reference run (needs token + explicit approval), same frozen files, separate column.
11. Report: three layers separated, no single headline; recommendation: adopt as an *optional* backend behind config, remain `null` by default; calibration work stays R3.3.
12. Stop; await review before any commit/merge or change to production defaults.

Estimated resource budget for Phase 2B (ESTIMATED): disk 8–10 GiB (Decider ≈ 7–8 GiB incl. venv + Kev-0.8B ≈ 3–4 GiB; free: 60 GiB); RAM ≤ 6 GiB per run, one model at a time; network ≈ 6–9 GiB one-off download; wall-clock ≈ 4–8 h including held-out construction; API spend: $0 unless the hosted reference is authorised (≈ $0.03–$0.20).

---

## 11. Unresolved questions / risks

1. **Turkish quality: UNKNOWN for every candidate** (Qwen3.5 bases are multilingual; Decider/Kev training data are mostly English). The held-out set is designed to measure it; a failure is a legitimate NO-GO for Turkish routing.
2. **Kev hash discrepancy:** README lists “Hub revision `9a45d25e`” for Kev-0.8B; HF refs show `v1.0 → 788ddbdd65` and `main → bf75a6a884`. Possibly the README names a different object (e.g., an adapter blob). Must be reconciled with the GitHub release checksums before install.
3. **Pickle weights:** Kev `head.pt` (and `slot_head.pt` in Decider local save format) are pickles; Decider’s published `head.safetensors` is safer. Never `torch.load` without `weights_only=True`.
4. **Dependency weight:** `torch>=2.7`, `transformers>=5.15`, `peft>=0.21` (+ mlx-lm pinned) — not measured; Python-wheel provenance/hash-pinning needed; some packages may require a native build.
5. **Young projects:** all repos < 6 weeks old, fast-moving `main`; pin SHAs and re-verify at install.
6. **Vendor-reported numbers:** JevBench, Decision Index, Mac latencies are maintainer-run on different Macs (M3 Pro / M4 Pro / M5). Treat as DOCUMENTED, not as predictions for an M4 16 GB.
7. **Look-alikes:** `kev-4b-merged` (third party), OpenRouter routes (hosted), Ollaya’s “Mapika decider” vs Strands Decider, many “OpenJev” repos, `pip install kev` (a different, unrelated ORM). Installing by name is forbidden; Phase 2B uses pinned SHAs only.
8. **Option text budget:** the adapter’s 4 KiB payload cap is smaller than any candidate’s context; richer `option_info` could help but is a contract change (not proposed).
9. **Confidence:** candidate probabilities are not calibrated *for our task*; they stay `kind="raw"` and are never used for execution (R3.3 later).
10. **Free tier / account for Cloudflare:** UNKNOWN (not checked); no token exists in this environment.
11. **Memory-pressure measurement** discrepancy (§4) carries over.
12. The Clef-Omni model/blog (“clef-faster-cheaper-multimodal”) appeared incidentally; not reviewed beyond metadata.

### Go/no-go recommendation (exact)

**GO (conditional) for Phase 2B limited to: held-out set construction + Strands Decider 2B v1-2610 install and evaluation.**
Kev-0.8B: second, only after the Decider smoke gate. Clef-Flash: reference only, requires separate explicit approval. **NO-GO** for Kev-4B/9B, Clef/Clef-Flash local, Jev, OpenJev, Ollaya, vLLM-Jev, Naive-N0.5-Flash.
No production default changes in any case.

---
---

# Phase 2A+ — Local SystemOne ecosystem consolidation (appended 2026-10-14, same day)

Scope unchanged: research only; no downloads of weights, no installs, no paid calls, no hooks/plugins installed, no production-default change,
Phase 1 evidence untouched, Laya runtime untouched, no commit. Sections 1–11 above are preserved; the only changes to them are the
documented corrections in A.0. Evidence labels as before. Sources are primary (HF/GitHub APIs, READMEs, vendor docs) unless marked **secondary**.
Tool/plugin review (part C) is README-level only: I did not read their source code.

## A.0 Corrections to sections 1–11 (new primary evidence)

| Earlier statement | Correction |
|---|---|
| §9: OpenJev “best-known ones are a method … not a trained decision model” | Partly wrong. `IamBusy/OpenJev-0.6B` **is** a trained checkpoint (LoRA + scalar head on Qwen3-0.6B). `lookski/openjev` is a generic masked-logit engine; `Shalimov04/open-jev` is a teacher→student pipeline; `ZefanCai/Open-Jev-2B` is another trained checkpoint. “OpenJev” remains a shared name — see A.1. |
| §9: vLLM-Jev “CUDA-oriented; no Mac path verified” | Incomplete. README documents an **Apple Silicon preview** (macOS ≥ 15, Python 3.12, vLLM CPU wheel + vllm-metal 0.29.0, MLX/MPS). It supports Open-Jev-2B, OpenJev-0.6B, Laya, Valen; it does **not** list Decider or Kev; Clef is Linux-only. |
| §9: Naive “repo describes a coding/agent LLM” | Confirmed; added: ~315 GB FP8 weights, needs FP8-capable NVIDIA GPUs (A.4). |
| §1/§8 shortlist (Decider-2B, Kev-0.8B) | **Unchanged** after comparison (A.1). |

## A.1 Model candidate review — the four named leads

Taxonomy (the requested distinction):

| Lead | Class | Verified identity |
|---|---|---|
| `IamBusy/OpenJev-0.6B` | **1. Trained decision model** (experimental) | HF @ `b4bf78e7c053407b5d54a71bcc682ef5bbe59e72`, model revision 0.3.0; Apache-2.0; LoRA r8 (q,v) 1,146,880 params + 1,024-param scalar head; base `Qwen/Qwen3-0.6B` @ `c1899de289a04d12100db370d81485cdf75e47ca` (Apache-2.0, 751,632,384 params, 1.41 GiB); adapter 4.6 MB; loader = separate package `IamBusy/OpenJev` tag `v0.3.2` (not in your list; the model is unusable without it); no HF tags |
| `ZefanCai/Open-Jev-2B` | **1. Trained decision model** | HF @ `0c7aa498b1627be8da4acf34c863ff0ee0a92785`; weights Apache-2.0, code MIT (`Zefan-Cai/Open-Jev` HEAD `bd4118882f73…`, 412★); LoRA r8 + scalar head, adapter sha256 `2d23935b…`, head sha256 `3532cd57…`; base `Qwen/Qwen3.5-2B` @ `15852e8c16360a2fea060d615a32b45270f8a8fc` (2,274,069,824 params, 4.26 GiB, Apache-2.0); 20,204 steps, 80,816 rows; saved temperature 1.5188 |
| `lookski/openjev` | **2. Generic masked-logit engine** | MIT, 5★, created 2026-09-22, no weights; any HF causal LM (`LocalJev`), any OpenAI-compatible logprobs endpoint, or a TypeSafe client. Its own table shows ~1.2 s on CPU fp32 for Qwen3-0.6B (3 forward passes, 338 tokens); probabilities are raw softmax of an untrained LLM. Anthropic APIs can’t be used (no logprobs) |
| `Shalimov04/open-jev` | **3. Teacher/student training pipeline** | MIT, 1★, pushed 2026-10-11; YAML task → LLM teacher soft labels (one constrained letter token) → distil `mmBERT-small` (~140 M encoder) → calibrate (500 held-out rows) → serve `/v1/systemone`. **One fixed label set per trained student** (“not a general model that takes options at request time”) |

Dynamic-option support and shape of each:

| | Options at request time | Cross-option interaction | Notes |
|---|---|---|---|
| OpenJev-0.6B | yes; each candidate scored independently by a shared scalar head (255-candidate run test) | **none by design** → order-equivariance by construction (reported 100 % consistency on 48 swap tests) | Cannot weigh options against each other; `unknown` must be an explicit candidate |
| Open-Jev-2B | yes (candidate scoring, 4,096 tokens per candidate) | independent scoring (same family) | Server defaults to loopback 127.0.0.1:8791 |
| Decider / Kev (shortlist) | yes (pointer head over option end-tokens) | options share the context; Kev warns order can change answers | |
| lookski | yes (letter/answer-token mask) | full (the LLM sees all options) | untrained for the task |
| Shalimov04 student | **no** (fixed labels) | n/a | would need a fixed universe + mask (A.6) |

Hardware, runtime, evidence (Apple M4 16 GB):

| | Download (ESTIMATED from verified file sizes) | Runtime | Mac evidence | Quality evidence |
|---|---|---|---|---|
| OpenJev-0.6B | ≈1.4 GiB base + 4.6 MB (+ venv: torch≥2.6, transformers **4.57.x pin**, peft<0.19; Python 3.12 recommended — not installed here) | MPS bf16 / CPU fp32; no CUDA | M3 Pro 36 GB (author) | Own tests, N = 15–64 per task; trained on **725 rows**; improves some tasks, regresses others (banking unseen 93.8→78.1 %, verify 67→50 %); author calls it “optional experimental backend” |
| Open-Jev-2B | ≈4.3 GiB base + 10 MB | MPS **fp32** (`JEV_TORCH_DTYPE=float32`, opt-in) or CPU; MLX only through vLLM-Jev preview | no Mac latency numbers found | Author-run synthetic: test 94.7 % hard acc (10,532), OOD 86.0 % (15,920), ECE 0.012/0.106; **no baseline run** (“does not establish training gain”); no GPU re-run at upload |
| Decider 2B v1 (shortlist #1) | ≈4.5 GiB | MLX documented | M4 Pro, v19 | JevBench 180/231 (maintainer), third-party Ollaya lists a *different* “decider” at 0.591 typed-decisions — do not mix |
| Kev-0.8B (shortlist #2) | ≈1.7 GiB | MLX documented | M5 | held-out index 23.3; new-source acc 0.648 |

RAM note (ESTIMATED): Open-Jev-2B in fp32 = 2.27 B × 4 B ≈ 9.1 GiB weights → leaves < 7 GiB for macOS and everything else on 16 GB; bf16/MLX not documented by the author. This is the main reason it is not shortlisted for the M4.

**Comparison and decision.** OpenJev-0.6B is cheap and order-equivariant by construction, but its training set is tiny (725 rows), its own report shows regressions, and it is the only leading candidate whose maintainers call it experimental. Open-Jev-2B has the largest training run but only author-run synthetic evaluation without a baseline, and needs ≈9 GiB on this Mac. Decider/Kev have maintainer-run public benchmarks (JevBench, Decision Index on frozen suites) and documented MLX paths. None of the four new leads provides independent evidence that outperforms them on our failure mode (label preference / ignoring descriptions).

**Final immediate local candidates: unchanged — (1) Strands Decider 2B v1-2610, (2) Kev-0.8B v1.0.**
Reserves, in order: **Open-Jev-2B** replaces Kev-0.8B if the Kev pickle/tag check fails or Kev-0.8B fails the Decider-style smoke gate for a non-fundamental reason (only if RAM headroom is confirmed on the M4 — it needs a bf16/MLX route or ≥ 9 GiB); **OpenJev-0.6B** is a KEEP-AS-REFERENCE structural control (it answers “does pure candidate-independent scoring fix order consistency, and at what accuracy cost?”) and is not installed. Generic masked-logit engines are reference only (they have no trained head).

## A.2 Serving runtimes vs. the native Laya-MLX adapter

| | Native adapter (today) | Ollaya `ollaya-dev/ollaya` v0.13.0 | vLLM-Jev `mode-io/vllm-jev` |
|---|---|---|---|
| License / stars / push | internal | Apache-2.0, 1,305★, 2026-10-13 | Apache-2.0, 524★, 2026-10-12 |
| Form | per-backend subprocess, JSON lines v1, scrubbed env, offline | Rust daemon (ONNX Runtime CPU/CUDA; llama.cpp for GGUF, Metal on Apple silicon), HTTP `127.0.0.1:11435`, Ollama-like CLI | Python on vLLM; CUDA on Linux; **Apple Silicon preview** (vllm-metal, MLX/MPS) |
| `/v1/systemone` TypeSafe wire | no (internal contract) | yes (+ `/api/decide`, `/v1/decisions`) | yes (`127.0.0.1:8795`) |
| Exact checkpoints we care about | Laya-MLX (installed) | `laya`, `laya:en/multilingual/typed-decisions`, `kev(:0.8b/:9b)`, `clef` (Flash 9B), `decider` = **Mapika’s, not Strands**, Winnow, etc.; not Strands Decider | Mac: Open-Jev-2B, OpenJev-0.6B, Laya family, Tiny-Jev, Valen-Preview; Linux only: Open-Jev-9B, vjev, rsi-jev, JevAny, Clef/Clef-Flash — **no Decider, no Kev on either** |
| Mac M4 16 GB | yes (measured) | supported (macOS arm64 installer); decoder models via ONNX-CPU or GGUF-Metal; Laya via ONNX CPU, not MLX | macOS ≥ 15, requires **Python 3.12** + vLLM CPU wheel + vllm-metal; preview |
| Linux/CUDA | n/a | yes (CUDA 12/13 runtime installed by script) | yes — its main purpose |
| Offline | yes | after `pull`; `OLLAYA_MODELS` selects the store (default location not verified); pulls from the model authors’ HF repos pinned by commit + sha256 | after first prepare |
| Install | repo-local venv, hash-pinned | `curl -fsSL https://ollaya.dev/install.sh \| sh` (+ desktop app, Docker) — a remote script piped to a shell; supply-chain review required, not run | `source scripts/install_mac.sh` (downloads Python 3.12 via uv and release wheels from GitHub) |
| Security | no listener | binds loopback; **no auth by default**; `OLLAYA_API_KEY` bearer; Host/Origin checks; non-loopback bind warns but starts; `pull/delete/create` exposed over the same port | loopback default; `--host` flags standard vLLM; auth not verified |
| Duplication | one model store | would **re-download Laya** as its own ONNX package (derived files) beside our 678 MB Laya-MLX store; per-model runner processes | would store a prepared checkpoint per model |
| MCP / skills | none | `ollaya mcp` (stdio MCP) and `ollaya-decisions` skill (`npx skills add …`) | none |
| Integration cost for Agent OS | low (done) | new `ollaya` backend = HTTP adapter (new transport, listening socket) | same, plus Python-3.12 environment |

Verdict:
* **Neither is the first benchmark.** The native path is the only way to run the *shortlisted* Decider (MLX) and it adds no daemon. vLLM-Jev does not serve Decider/Kev at all and is a Mac preview with heavy prerequisites → **DEFER on Mac; KEEP AS REFERENCE for Linux/CUDA**.
* If one runtime experiment is wanted later, **Ollaya is the better first optional experiment** (single binary, loopback, key option, Kev + Laya available, parity claims published) — as a *Phase 2C* isolated test after the native Decider result, with `OLLAYA_MODELS` pointed into a repo-local directory, `OLLAYA_API_KEY` set, and the install script reviewed first. It must not become mandatory and must not replace `system_one()`; at most a new entry in `config/systemone.yaml`.
* Ollaya’s published numbers are third-party-to-us and not audited here.

## A.3 MCP, skills and ecosystem tools

Existing Agent OS functionality used for the overlap column: deterministic router and policy (`router.py`, `permissions.py`), capability plane with exposure whitelist for MCP via `--strict-mcp-config` (`config/mcp.yaml`), worker verification + retry/resume (`docs/architecture.md`), human approval for high risk and canonical writes (`routing.yaml`, `knowledge.yaml`), protected-manifest, git pre-push hook, JSONL telemetry (`agentos/telemetry.py`), Hermes as sole orchestrator. No compaction/context pruning exists (that is the deferred ContextGate).

| Component (primary check) | What it does | Needs | Overlap / risk | Decision |
|---|---|---|---|---|
| `louis-szeto/open-jev-bridge` (MIT, 0★, v0.5.0) | Node MCP server + Claude Code/Codex hooks: verbatim compaction, **completion Stop checks**, ten judgment tools; any `/v1/systemone` backend (Jev, Kev, Laya, local llama.cpp) | Node, hosts’ hook installation, optional key file | Duplicates MCP exposure policy, verification, completion gating and compaction in one plugin; Stop-hook checks can block/force continuation outside Agent OS’s verifier; competes with Hermes orchestration | **REJECT** as a component. Pattern worth keeping: backend-agnostic `doctor` transport/shape check |
| `jkudish/jev-mcp` (MIT, 523★) | 12 judgment MCP tools (verify, screen, rerank, review, audit …) | Node ≥ 22, **TypeSafe API key** (cloud) by default | Redundant MCP server; sends text to a cloud; `jev_review`/`jev_verify` would compete with the deterministic verifier | **REJECT**; adapt pattern: “claim ↔ evidence + same_subject question” as a *future* verifier probe |
| LiteLLM Jev routing (**secondary only**: `prismhq/jev-router`, others; no official LiteLLM doc verified) | Pre-call hook routes requests to model lanes via Jev | LiteLLM, Jev | Duplicates router; a pre-call hook that picks the model is exactly what the Agent OS router owns | **REJECT** (pattern: lane routing already in `routing.yaml`) |
| Vercel `experimental_evaluate` (**secondary only**: articles on `@ai-sdk/typesafe-ai`, AI Gateway `typesafe-ai/jev`) | TS API for evaluation models | Node, Vercel AI SDK, gateway key | Not Python; cloud | **KEEP AS REFERENCE** (API shape only) |
| Pydantic AI `TypeSafeModel` | **UNRESOLVED** — no primary source found | – | – | **REJECT** (cannot verify) |
| `shitianfang/wakegate` (MIT, 6★) | One Jev call decides whether to wake a sleeping agent; **fail-open** | Vercel AI SDK + Gateway key | Fail-open contradicts Agent OS fail-closed/escalate rule; no sleeping-agent concept here | **DEFER**; later Hermes-level pattern *adapted to escalate-on-error* |
| `tamaratran/fast-jev-compaction` (MIT, 7,617★) | Claude Code function-hook plugin; deletes stale tool calls/results using Jev | `TYPESAFE_API_KEY`, `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` in global `settings.json` (early-access) | Global hook; deletes evidence before verification; cloud; = ContextGate territory | **DEFER to ContextGate** (benchmark a local backend later); do not install |
| `tamaratran/jev-pruner` (MIT, 163★) | Hook trims Bash output > 10 k tokens before the model sees it | key + Claude Code hook | Same; modifies tool results seen by workers; could hide verifier output | **DEFER to ContextGate** |
| `kitze/unclutter` (MIT, 372★) | Browser extension removing page clutter via Jev | key (Gateway/TypeSafe) | None | **REJECT** (out of scope) |
| `browser-use/jev-ultrafast` (MIT, 22.8k★) | Browser agent: Jev picks operation + element from a dynamic indexed action table | TypeSafe key, OpenRouter key | Competing orchestrator for browsing; cloud; paid. Useful note: its `DONE` still needs independent outcome verification | **KEEP AS REFERENCE** (dynamic options pattern) |
| `ChenneyZhuang/laya-browser-agent` (Apache-2.0, 20★) | Laya (MLX/PyTorch) + `/v1/systemone` shim for browser agents; own Laya fine-tunes | torch/MLX | Third-party Laya variants; browser use-case, not worker routing | **KEEP AS REFERENCE**; could inform a later non-Qwen Laya control |
| Ollaya `ollaya mcp` + `ollaya-decisions` skill | MCP and skill so agents call local decision models | Ollaya daemon, `npx skills add` | Second MCP exposure path and an agent-facing skill telling agents when to decide — bypasses Hermes→router; global skill install | **DEFER with Ollaya (Phase 2C only)**; never install the skill globally; any exposure through `config/mcp.yaml` whitelist with a reviewed profile |

Cross-cutting findings: (1) almost all tools hard-require a **cloud TypeSafe/Gateway key**, so they fail the local-first constraint unless pointed at a local `/v1/systemone` backend; (2) the hooks (compaction, pruner, Stop checks) change what workers *see* or when they *stop* — they would sit outside the capability plane and the protected manifest; (3) the only item with immediate value is the **wire-compat insight**: a local `/v1/systemone` shim is how most of this ecosystem would attach later, so a thin optional shim could be built *behind* `system_one()` without making it the contract. No hooks or plugins were installed.

## A.4 Naive-N0.5-Flash and a custom Hermes System-1 (future research only)

Verified (`NaiveAI-Labs/Naive-N0.5-Flash`, HEAD `3551de41a35f…`; HF `NaiveAI/Naive-N0.5-Flash` @ `0235b3b5ff27…`): MIT; 309 B MoE, 15.5 B active; 1 M context; built on Xiaomi MiMo-V2.5 + DeepSeek sparse attention; **requires FP8-capable NVIDIA GPUs, weights ≈ 315 GB** (HF repo 575 GiB across 70 files); inference via its own NaiveRT system (claim: up to 2,000 tok/s). API: “will also be provided”, announced at $0.10 in / $0.40 out / $0.01 cache-read per M tokens — **availability not verified, no account, nothing called**. **The “custom Jev/Tetris experiment” appears nowhere in the repo README or in a web search → UNVERIFIED, not relied on.** Verdict: **KEEP AS REFERENCE / future teacher candidate only**; cannot run locally (M4 16 GB or this repo’s hosts).

Teacher alternatives (all UNEVALUATED here): Clef-Flash (Apache-2.0, hosted $0.038/M), a strong LLM with logprobs, human experts; the teacher must not be the model under test.

Feasibility sketch of **Hermes telemetry → privacy filter → expert labels → teacher comparison → student → held-out → calibration** (no data collected, nothing trained):
1. Source: `state/telemetry/*.jsonl` already records route, worker, model, success, quality, human_corrections, fallbacks (null when unmeasured). It holds **outcomes, not the routing request text**; adding request text is a *new collection* (not authorised, needs a privacy design: redaction, local-only storage, retention, opt-in per task).
2. Volume reality check (ESTIMATED): a single-user stack produces tens of routing decisions per week; Shalimov04’s students used 750–8,000 training rows; OpenJev-0.6B used 725. Real telemetry alone would not suffice for months → synthetic scenario generation from `workers.yaml` + registry is mandatory, which is what §7 already proposes.
3. Labels: expert-reviewed gold (acceptable set / forbidden set / escalate) as in the held-out design; teacher soft labels only as a *second* signal, never as gold.
4. Student: Shalimov04-style distillation (KL to teacher, then temperature/bias calibration on ~500 rows) is the only open pipeline we found; its own caveats: calibration is to *gold on its own task*, fixed K.
5. Evaluation: frozen held-out first (§7), then calibration under R3.3 (`kind="calibrated"` only after an accepted calibration record).

**Fixed label set vs runtime-defined eligible options** — the central design decision:
* Our eligible options change per request (policy eligibility, capability requirements) and the worker roster changes over time. A closed-class student (Shalimov04, Laya-style classifier) learns *worker ids* — the same label-prior failure seen in Phase 1 (label-prior baseline 0.714).
* Two viable shapes: (a) **candidate-scoring/pointer model** over option text (Decider, Kev, Open-Jev, OpenJev) — handles dynamic sets, needs descriptions to carry meaning; (b) **fixed-universe classifier with masking** over the full configured worker set, masked to the eligible subset — small and fast, but retrain on every roster change and brittle to unseen workers; only acceptable if roster changes are rare and evaluated.
* Recommendation for future research: prefer (a) — fine-tune or distil a pointer/candidate-scoring student on aliased worker ids (randomised labels), keep (b) only as a baseline.
No training, telemetry collection, or data export is proposed for Phase 2B.

## A.5 Consolidated decision matrix

| Item | Decision | One-line reason |
|---|---|---|
| Strands Decider 2B v1-2610 | **INSTALL / BENCHMARK NEXT (#1)** | Decoder + pointer head; documented MLX; maintainer-run public benchmarks; fits 16 GB |
| Kev-0.8B v1.0 | **INSTALL / BENCHMARK NEXT (#2, after #1 smoke)** | Smallest documented-for-any-Mac decoder candidate; different author/recipe; pickle + tag checks first |
| Open-Jev-2B | **KEEP AS RESERVE** | Large training run but only author-run synthetic eval; fp32/MPS ≈ 9 GiB RAM est. |
| OpenJev-0.6B | **KEEP AS REFERENCE** | Order-equivariant by design; tiny training set; experimental; transformers pin conflicts with Decider’s |
| lookski/openjev | KEEP AS REFERENCE | Untrained masked-logit engine; useful as an untrained-LLM control |
| Shalimov04/open-jev | KEEP AS REFERENCE | Only open distillation pipeline; fixed-label students |
| Clef-Flash (hosted) | KEEP AS REFERENCE (needs explicit approval) | Quality ceiling; $0.038/M |
| Clef / Clef-Omni / Kev-4B+ | REJECT (local) | Do not fit 16 GB |
| Ollaya | **DEFER → first optional runtime experiment (Phase 2C)** | Best single-binary runtime; daemon + curl-pipe install + duplicate Laya store |
| vLLM-Jev | DEFER on Mac / REFERENCE on Linux-CUDA | Doesn’t serve Decider/Kev; Mac preview with Python 3.12 + vLLM CPU wheels |
| Naive-N0.5-Flash | KEEP AS REFERENCE (future teacher) | 315 GB FP8, NVIDIA only; API unverified; Jev/Tetris claim unverified |
| open-jev-bridge, jev-mcp | REJECT | Redundant MCP/verification/compaction; cloud key |
| fast-jev-compaction, jev-pruner | DEFER → ContextGate | Global hooks; change worker-visible context |
| wakegate | DEFER (adapt as escalate-on-error) | Fail-open |
| LiteLLM routing, Pydantic AI TypeSafeModel, Vercel experimental_evaluate | REJECT / UNRESOLVED / REFERENCE | Duplicate router / unverifiable / TS cloud API |
| Unclutter | REJECT | Out of scope |
| jev-ultrafast, laya-browser-agent | KEEP AS REFERENCE | Dynamic action-space patterns |
| Jev (hosted), Mapika “decider”, OpenJev look-alikes | REJECT / UNRESOLVED | Cloud / unverified / ambiguous names |

Final answers to the requested list:
1. **Two local candidates:** Strands Decider 2B v1-2610; Kev-0.8B v1.0 (reserve: Open-Jev-2B).
2. **First optional serving-runtime experiment:** Ollaya, isolated, Phase 2C only, after the native Decider result. vLLM-Jev not on Mac.
3. **MCP/skill integration:** none now. No global hooks/skills/plugins. Revisit `ollaya mcp` only through a reviewed `config/mcp.yaml` profile; compaction/pruner patterns go to ContextGate.
4. **Disk/RAM (ESTIMATED):** unchanged for Phase 2B (≈ 8–10 GiB disk, ≤ 6 GiB RAM per run). Add-ons if authorised: Ollaya binary + its own ONNX store (Laya ≈ 0.4–1 GiB duplicate; Kev/Decider ONNX CPU sizes UNKNOWN); Open-Jev-2B reserve ≈ 4.3 GiB disk / ≈ 9 GiB RAM (fp32); OpenJev-0.6B ≈ 1.4 GiB / ≈ 2–3 GiB.
5. **Overlap with existing functionality:** see A.3 column; the router, capability-plane MCP whitelist, verifier/retry, approval flow and telemetry already cover routing, tool exposure, verification, retries and recording; only compaction/pruning is not covered (deferred).
6. **Phase 2B sequence:** §10 unchanged (1 held-out set → 2 Decider verification → 3 install → 4 worker+backend → 5 smoke gate → 6 operational → 7 dev eval → 8 held-out once → 9 Kev-0.8B → 10 optional hosted Clef-Flash reference); inserted before 9: if Kev pre-install checks fail, swap in Open-Jev-2B only after a RAM check; **Phase 2C (separate authorization):** Ollaya isolated runtime experiment on the same frozen files, comparing `/v1/systemone` vs native adapter overhead.
7. **Deferred:** ContextGate (compaction, pruning, Stop-hook/completion checks, wakegate) and Custom Hermes-System1 (telemetry collection design, teacher selection, student training, R3.3 calibration) — no work started.
8. **Blockers and go/no-go:** unchanged from §11 plus: (i) Open-Jev-2B has no Mac latency/RAM evidence; (ii) OpenJev-0.6B loader pins `transformers<4.58` (incompatible with Decider’s `>=5.15`) → separate venvs; (iii) Ollaya/vLLM-Jev installers pipe/download remote code; (iv) LiteLLM/Vercel/Pydantic claims rest on secondary sources; (v) Naive API availability and its Jev/Tetris claim unverified. **Go/no-go: conditional GO for Phase 2B exactly as in §11 (held-out set + Decider, then Kev-0.8B). NO-GO for any runtime, hook, MCP, plugin, telemetry or training work until separately authorised.**

### A.6 Additional sources (accessed 2026-10-14)
* https://huggingface.co/api/models/IamBusy/OpenJev-0.6B?blobs=true , `…/raw/main/{README,RESULTS,MANIFEST.json,adapter_config.json}`
* https://huggingface.co/api/models/ZefanCai/Open-Jev-2B?blobs=true , `…/raw/main/{README,UPSTREAM}.md`; https://raw.githubusercontent.com/Zefan-Cai/Open-Jev/HEAD/docs/deployment.md
* https://github.com/lookski/openjev ; https://github.com/Shalimov04/open-jev ; https://github.com/IamBusy/OpenJev (pyproject at tag `v0.3.2`; GitHub API returned a 301 redirect, README content via HF card)
* https://github.com/ollaya-dev/ollaya (README, `docs/api.md` §14 Security, `skills/ollaya-decisions/SKILL.md`); https://github.com/mode-io/vllm-jev (README, `scripts/install_mac.sh`)
* https://github.com/louis-szeto/open-jev-bridge ; https://github.com/jkudish/jev-mcp ; https://github.com/tamaratran/fast-jev-compaction ; https://github.com/tamaratran/jev-pruner ; https://github.com/shitianfang/wakegate ; https://github.com/kitze/unclutter ; https://github.com/browser-use/jev-ultrafast ; https://github.com/ChenneyZhuang/laya-browser-agent
* https://github.com/NaiveAI-Labs/Naive-N0.5-Flash ; https://huggingface.co/api/models/NaiveAI/Naive-N0.5-Flash?blobs=true
* **Secondary**: web search for LiteLLM / Vercel `experimental_evaluate` / Pydantic AI (e.g. vercel.com/kb/guide/typesafe-jev-and-ai-sdk, flaviocopes.com/jev-vercel-ai-sdk) — not relied on for decisions beyond “REFERENCE/REJECT”.

---

## A.7 Phase 2A+ closure review (2026-10-14, R3.2C execution session)

Independent re-check of sections 1–11 and A.0–A.6 against primary sources before any candidate scoring. Corrections are applied in place
above where marked; this table is the record.

| Topic | Finding | Status |
|---|---|---|
| Strands vs Mapika Decider | Strands Decider = `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` (Strands Labs, Apache-2.0). Ollaya’s `decider` / `decider:4b` / `decider:0.8b` / `decider:2b-vision` are attributed to **Mapika** in Ollaya’s README and licence list — a different author and recipe. Nothing in this milestone uses the Mapika models. | VERIFIED (no change) |
| Decider v1 LoRA rank | `lora/adapter_config.json` at `216d1ccb…`: r = **48**, α = 96, 12 target modules (attention, MLP and Gated-DeltaNet projections), no DoRA, no `modules_to_save`. README’s “rank-16” refers to earlier releases. `strands_decider_config.json`: pointer head (pointer_dim 768), max_length 4096, bf16, temperature_by_kind {choice 0.863, noul 1.070, score 1.834}. | **CORRECTED** (§2) |
| Decider base revision | `provenance.json` records `base_model_revision b1485b2fa6dfa1287294f269f5fb618e03d52d7c` (“inferred: Hub main at training time; hosts did not pin it”). The loader (`modeling.base_revision`) reads it and calls `snapshot_download(base, revision=…)`, so the base is pinned at load. | VERIFIED (caveat: inferred by the maintainer) |
| Decider head format | `head.safetensors` (safetensors, sha256 `ace56742…`); `load_head_state` uses `safetensors.load_file`; a `slot_head.pt` path would use `torch.load(weights_only=True)`. No pickle is loaded for the published checkpoint. | VERIFIED |
| Decider MLX install | PyPI 0.1.0 has no `mlx` extra; the pinned git commit `8b6faa55…` declares `mlx = [mlx>=0.32.2, mlx-lm>=0.32,<0.33]` (darwin/arm64). `requires-python >=3.10`: the existing uv-managed CPython 3.11.13 is sufficient — **no Python 3.12 is needed**. Version comes from setuptools-scm (git describe); a source install needs `SETUPTOOLS_SCM_PRETEND_VERSION`. | **CORRECTED** (§4 implied 3.12) |
| Decider footprint | Full footprint = checkpoint repo (≈ 0.22 GiB incl. 20 MB tokenizer and eval files) + base Qwen3.5-2B-Base (4.26 GiB, single safetensors) + venv. Adapter-only size (192.5 MiB) must not be quoted as the model size. Measured values: see the Decider evidence report. | CLARIFIED |
| vLLM-Jev support | Mac (MLX, or MPS for Laya): Open-Jev-2B, Laya, Laya-multilingual, Laya-typed-decisions, OpenJev-0.6B, Tiny-Jev, Valen-Preview. Linux only: Open-Jev-9B, vjev, rsi-jev, JevAny, Clef, Clef-Flash. Neither Decider nor Kev. Install script fetches Python 3.12 via uv and vLLM 0.29.0 CPU + vllm-metal wheels from GitHub releases. | **CORRECTED** (A.2 row) |
| OpenJev distinctions | Trained: `IamBusy/OpenJev-0.6B` (r8 q/v LoRA + 1,024-param scalar head, 725 training rows), `ZefanCai/Open-Jev-2B` (r8 LoRA + scalar head, 80,816 rows). Engine (untrained): `lookski/openjev`. Pipeline (fixed labels): `Shalimov04/open-jev`. | VERIFIED (no change) |
| Kev revision / safe loading | Kev-0.8B LoRA is r16/α32 on `Qwen/Qwen3.5-0.8B-Base` with `revision: null` in `adapter_config.json` at both `main` and `v1.0`; `head.pt` is a pickle. The `9a45d25e` vs `788ddbdd` discrepancy is resolved (or not) in the Kev bring-up step, before any download of `head.pt`. | OPEN → Kev step |
| Laya baseline identity | Installed baseline = `aac6fef/laya-multilingual-mlx` @ `f2b4faf51023039425946074e2cf1361d2db11d5` (MLX port of `convaiinnovations/laya-multilingual`, mmBERT-base ≈ 322 M), runtime laya-mlx 0.4.0 — from `config/systemone.yaml`. Ollaya’s `laya:en` (ModernBERT-large, 421 M) is a **different** checkpoint and is not our baseline. | VERIFIED |

Unverified claims remain labelled as before (vendor/maintainer benchmarks = DOCUMENTED; Naive API and Jev/Tetris claim = UNVERIFIED;
LiteLLM/Vercel/Pydantic AI = secondary or UNRESOLVED). Review verdict: **report accepted with the corrections above; Phase 2A+ CLOSED.**
