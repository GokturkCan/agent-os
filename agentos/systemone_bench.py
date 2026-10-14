"""`agentos systemone smoke|bench` — measure a configured SystemOne backend (R3.2B).

  agentos systemone smoke --backend laya-mlx
  agentos systemone bench --backend laya-mlx -n 200 --warmup 10 --seed 1337 --out result.json

Measures operational properties only: cold start, warm decision latency (p50/p95/p99), sequential
throughput, valid-choice / malformed / escalation rates, worker RSS, and on-disk footprint. It does
NOT measure accuracy - there is no labeled dataset - and says so in its output. The workload is
synthetic, seeded and deterministic, so two runs are comparable and the hash of the decision
sequence shows whether the backend reproduces its own answers.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

from . import systemone as S
from . import systemone_adapter as A

SCHEMA = 1
TASK_TYPES = ("classification", "summarization", "research", "review", "coding")
CAPABILITIES = ("code.edit", "code.test", "code.references", "web.docs_lookup", "web.interact", "devops.github")
OPTION_SETS = (("claude_code", "codex"), ("claude_code", "codex"), ("codex", "claude_code"),
               ("claude_code",), ("codex",), ("claude_code", "codex", "deepseek_harness"))


def workload(n: int, seed: int) -> list[S.SystemOneRequest]:
    """`n` deterministic, compact worker-choice requests (operational state only)."""
    rng = random.Random(seed)
    reqs = []
    for i in range(n):
        tt = rng.choice(TASK_TYPES)
        caps = tuple(sorted(rng.sample(CAPABILITIES, rng.randint(0, 3))))
        reqs.append(S.SystemOneRequest(
            task_type=tt,
            questions=(S.Question("worker", "choose", "Which eligible worker should serve this task?"),),
            eligible_options=rng.choice(OPTION_SETS),
            state={"task_class": tt, "stage": "fastgate", "attempt": rng.randint(1, 3)},
            required_capabilities=caps, risk=rng.choice(("low", "low", "medium", "high")),
            resource_state={"msi": rng.random() < 0.3, "mac": True}))
    return reqs


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted list (q in [0, 100])."""
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _stats(ms: list[float]) -> dict:
    s = sorted(ms)
    return {"n": len(s), "min": round(s[0], 3), "p50": round(percentile(s, 50), 3),
            "p95": round(percentile(s, 95), 3), "p99": round(percentile(s, 99), 3),
            "max": round(s[-1], 3), "mean": round(sum(s) / len(s), 3)} if s else {"n": 0}


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _sh(*argv) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def environment(cfg) -> dict:
    mem = _sh("sysctl", "-n", "hw.memsize")
    return {"chip": _sh("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor(),
            "ram_gib": round(int(mem) / 2**30, 1) if mem.isdigit() else None,
            "machine": platform.machine(), "macos": platform.mac_ver()[0], "host_python": platform.python_version(),
            "agentos_commit": _sh("git", "-C", str(cfg.root), "rev-parse", "--short", "HEAD"),
            "agentos_tree_dirty": bool(_sh("git", "-C", str(cfg.root), "status", "--porcelain"))}


def footprint(cfg, name: str) -> dict:
    conf = A.definitions(cfg).get(name, {})
    runtime = (Path(cfg.root) / conf.get("runtime_dir", "state/runtime")).resolve()
    out = {"runtime_dir": conf.get("runtime_dir")}
    for label, sub in (("venv_bytes", "venv"), ("models_bytes", "models")):
        p = runtime / sub
        out[label] = _dir_bytes(p) if p.exists() else None
    known = [v for v in (out["venv_bytes"], out["models_bytes"]) if v is not None]
    out["total_bytes"] = sum(known) if known else None
    return out


def _fresh_backend(cfg, name: str):
    """A new (uncached) backend instance so cold start is really measured."""
    conf = A.definitions(cfg)[name]
    errors = A.validate_definition(name, conf)
    if errors:
        raise ValueError("; ".join(errors))
    return A.ADAPTERS[conf["adapter"]](name, conf, cfg)


def run_benchmark(cfg, name: str, *, n: int = 200, warmup: int = 10, seed: int = 1337, repeat: int = 20,
                  backend=None) -> dict:
    owns = backend is None
    backend = backend or _fresh_backend(cfg, name)
    reqs = workload(n + warmup, seed)
    rt = backend.runtime
    out: dict = {"schema": SCHEMA, "backend": name, "command": " ".join([os.path.basename(sys.argv[0]), *sys.argv[1:]]),   # no absolute local paths
                 "params": {"n": n, "warmup": warmup, "seed": seed, "repeat": repeat},
                 "environment": environment(cfg), "accuracy": None,
                 "accuracy_note": "not measured: no labeled dataset; valid_choice_rate is protocol/eligibility "
                                  "validity only"}
    try:
        # -- cold start: spawn -> ready (model load + warm-up) -> first decision
        t0 = time.perf_counter()
        first = backend.decide(reqs[0])
        cold_total = (time.perf_counter() - t0) * 1000
        out["cold_start"] = {"spawn_to_ready_s": getattr(rt, "startup_seconds", None),
                             "first_decision_incl_spawn_ms": round(cold_total, 1), "first_escalated": first.escalate}
        out["runtime"] = dict(getattr(rt, "info", {}) or {})
        rss = [rt.rss_kib()] if hasattr(rt, "rss_kib") else []
        # -- warm-up decisions (not measured)
        for r in reqs[1:warmup]:
            backend.decide(r)
        # -- measured sequential decisions
        lat, results, reasons = [], [], {}
        t_all = time.perf_counter()
        for i, r in enumerate(reqs[warmup:]):
            t = time.perf_counter()
            resp = backend.decide(r)
            lat.append((time.perf_counter() - t) * 1000)
            ans = resp.answer("worker")
            valid = (not resp.escalate and ans is not None and ans.choice in r.eligible_options)
            results.append((valid, ans.choice if valid else f"escalate:{resp.reason_code}", resp))
            if resp.escalate:
                reasons[resp.reason_code] = reasons.get(resp.reason_code, 0) + 1
            if hasattr(rt, "rss_kib") and i % 20 == 0:
                rss.append(rt.rss_kib())
        wall = time.perf_counter() - t_all
        if hasattr(rt, "rss_kib"):
            rss.append(rt.rss_kib())
        valid_n = sum(1 for v, _, _ in results if v)
        malformed = reasons.get("malformed-output", 0)
        out["warm_latency_ms"] = _stats(lat)
        out["throughput_decisions_per_s"] = round(len(lat) / wall, 2) if wall > 0 else None
        out["rates"] = {"valid_choice_rate": round(valid_n / len(results), 4) if results else None,
                        "malformed_response_rate": round(malformed / len(results), 4) if results else None,
                        "escalation_rate": round((len(results) - valid_n) / len(results), 4) if results else None,
                        "escalation_reasons": reasons}
        conf_vals = [r.answer("worker").confidence for _, _, r in results if not r.escalate]
        out["confidence"] = {"kinds": sorted({c.kind for c in conf_vals}),
                             "raw_min": round(min((c.value for c in conf_vals if c.value is not None), default=0), 4),
                             "raw_max": round(max((c.value for c in conf_vals if c.value is not None), default=0), 4),
                             "note": "raw scores only; never treated as calibrated probabilities"}
        out["choice_distribution"] = {k: sum(1 for _, c, _ in results if c == k) for k in sorted({c for _, c, _ in results})}
        out["decision_sequence_sha256"] = hashlib.sha256(
            json.dumps([c for _, c, _ in results]).encode()).hexdigest()
        out["latency_samples_ms"] = [round(x, 3) for x in lat]
        # -- self-consistency: the same request must give the same answer
        same = [backend.decide(reqs[warmup]) for _ in range(repeat)]
        distinct = {(r.answer("worker").choice if not r.escalate else r.reason_code) for r in same}
        out["repeat_consistency"] = {"repeats": repeat, "distinct_answers": len(distinct)}
        rss = [x for x in rss if x]
        out["memory"] = {"worker_rss_mib_min": round(min(rss) / 1024, 1) if rss else None,
                         "worker_rss_mib_peak_sampled": round(max(rss) / 1024, 1) if rss else None}
        out["footprint"] = footprint(cfg, name)
    finally:
        if owns:
            backend.close()
    return out


def add_parser(sub) -> None:
    sp = sub.add_parser("systemone", help="smoke-test / benchmark a configured SystemOne backend")
    ssub = sp.add_subparsers(dest="so_cmd", required=True)
    sm = ssub.add_parser("smoke")
    sm.add_argument("--backend", required=True)
    bn = ssub.add_parser("bench")
    bn.add_argument("--backend", required=True)
    bn.add_argument("-n", type=int, default=200)
    bn.add_argument("--warmup", type=int, default=10)
    bn.add_argument("--seed", type=int, default=1337)
    bn.add_argument("--repeat", type=int, default=20)
    bn.add_argument("--out", help="write the full JSON result here")


def run(cfg, a) -> int:
    if a.backend not in A.definitions(cfg):
        print(f"unknown configured backend {a.backend!r} (configured: {sorted(A.definitions(cfg))})")
        return 2
    if a.so_cmd == "smoke":
        b = _fresh_backend(cfg, a.backend)
        try:
            req = workload(1, 1)[0]
            resp = S.system_one(req, b)
            ans = resp.answer("worker")
            print(json.dumps({"backend": a.backend, "options": list(req.eligible_options), "escalate": resp.escalate,
                              "reason_code": resp.reason_code,
                              "choice": ans.choice if ans else None,
                              "confidence": {"kind": ans.confidence.kind, "value": ans.confidence.value} if ans else None,
                              "runtime": getattr(b.runtime, "info", {}),
                              "spawn_to_ready_s": getattr(b.runtime, "startup_seconds", None)}, indent=2))
            return 0 if not resp.escalate else 1
        finally:
            b.close()
    res = run_benchmark(cfg, a.backend, n=a.n, warmup=a.warmup, seed=a.seed, repeat=a.repeat)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    summary = {k: res[k] for k in ("backend", "cold_start", "warm_latency_ms", "throughput_decisions_per_s", "rates",
                                   "memory", "footprint", "repeat_consistency", "decision_sequence_sha256")}
    print(json.dumps(summary, indent=2))
    return 0
