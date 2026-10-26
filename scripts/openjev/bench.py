"""Operational measurements for the Open-Jev scorer on THIS Mac (R3.2H): cold start, warm latency, memory, determinism, perturbation robustness, lazy lifecycle.
Run ONLY while no other model process is running. Uses opt-partition requests (never the frozen final). Refuses to overwrite its output.
"""
import json
import re
import statistics
import subprocess
import time
from pathlib import Path

from agentos import config as C, systemone_eval as E, openjev_opt as O

OUT = Path("audit/openjev-v3/bench.json")
cfg = C.load()
data = E.load_dataset(Path("evals/data/openjev-v3-opt.yaml"))
reqs, seen = [], set()
for c in data["cases"]:
    if c["gold"].get("escalate") or c["lang"] != "en" or len(c["request"]["eligible_options"]) != 2:
        continue
    r = E.build_request(cfg, c, tuple(c["request"]["eligible_options"]), "described")
    key = json.dumps([r.state, list(r.eligible_options)], sort_keys=True, default=str)
    if key not in seen:
        seen.add(key)
        reqs.append((c, r))
reqs = reqs[:120]


def sh(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout
    except Exception as exc:
        return f"error: {exc}"


def mem(pid):
    fp = sh(["footprint", "-p", str(pid)]) if pid else ""
    rss = sh(["ps", "-o", "rss=", "-p", str(pid)]).strip() if pid else ""
    free = O.system_free_percent()
    m = re.search(r"Footprint:\s*([\d.]+\s*\w+)", fp)
    pk = re.search(r"phys_footprint_peak:\s*([\d.]+\s*\w+)", fp)
    return {"rss_mib": round(int(rss) / 1024, 1) if rss.isdigit() else None, "footprint": m.group(1) if m else None,
            "footprint_peak": pk.group(1) if pk else None, "system_free_percent": free, "raw_footprint_head": fp[:600]}


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 1)


out = {"host": sh(["sysctl", "-n", "machdep.cpu.brand_string"]).strip(), "ram_bytes": int(sh(["sysctl", "-n", "hw.memsize"]) or 0),
       "requests": len(reqs), "free_percent_before": O.system_free_percent()}
client = O.ScoreClient(cfg, cache_path=None)
try:
    base = O.OpenJevBackend(client, "baseline")
    t0 = time.perf_counter()
    first = base.decide(reqs[0][1])
    out["cold_start_first_decision_s"] = round(time.perf_counter() - t0, 2)
    out["worker_ready"] = dict(client.runtime.info)
    out["startup_seconds_runtime"] = client.runtime.startup_seconds
    pid = client.runtime.pid
    out["memory_after_first"] = mem(pid)
    lat = []
    for _, r in reqs[1:]:
        t = time.perf_counter()
        base.decide(r)
        lat.append((time.perf_counter() - t) * 1000)
    out["warm_baseline_ms"] = {"n": len(lat), "p50": pct(lat, .5), "p95": pct(lat, .95), "p99": pct(lat, .99), "max": round(max(lat), 1),
                               "mean": round(statistics.mean(lat), 1), "worker_ms_p50": pct(client.model_ms[1:], .5)}
    out["memory_after_warm"] = mem(pid)
    # ensemble = two scoring calls per decision
    ens = O.OpenJevBackend(client, "ensemble")
    lat2 = []
    for _, r in reqs[:40]:
        t = time.perf_counter()
        ens.decide(r)
        lat2.append((time.perf_counter() - t) * 1000)
    out["warm_ensemble_ms"] = {"n": len(lat2), "p50": pct(lat2, .5), "p95": pct(lat2, .95), "note": "alias call is uncached here; canonical call may hit the in-process cache"}
    # determinism: same requests again with the cache cleared
    probs1 = [list(t["probs"]) for t in base.trace[1:31]]
    keys1 = [t["choice"] for t in base.trace[1:31]]
    client.cache.clear()
    b2 = O.OpenJevBackend(client, "baseline")
    for _, r in reqs[1:31]:
        b2.decide(r)
    dmax = max(abs(a - b) for p, q in zip(probs1, [t["probs"] for t in b2.trace]) for a, b in zip(p, q))
    out["determinism"] = {"requests": 30, "max_abs_prob_diff": dmax, "decision_changes": sum(a != t["choice"] for a, t in zip(keys1, b2.trace))}
    # perturbation robustness (benign edits to the task summary)
    perts = {"trailing_space": lambda s: s + " ", "uppercase": lambda s: s.upper(), "thanks_suffix": lambda s: s + " Thanks!", "no_period": lambda s: s.rstrip(".")}
    rob = {}
    for name, fn in perts.items():
        flips = n = 0
        for (c, r), t in list(zip(reqs[1:41], base.trace[1:41])):
            st = dict(r.state)
            st["summary"] = fn(st["summary"])
            r2 = O.S.SystemOneRequest(**{**r.__dict__, "state": st})
            d = O.OpenJevBackend(client, "baseline").decide(r2)
            n += 1
            flips += (d.answer("worker").choice if not d.escalate else None) != t["choice"]
        rob[name] = {"n": n, "decision_flips": flips}
    out["perturbation_robustness"] = rob
    out["memory_final"] = mem(pid)
    out["client_calls"] = client.calls
finally:
    client.close()

# lazy lifecycle: idle exit then lazy restart
lz = O.ScoreClient(cfg, cache_path=None, idle_exit_seconds=6.0)
try:
    lb = O.OpenJevBackend(lz, "baseline")
    t = time.perf_counter()
    d1 = lb.decide(reqs[0][1])
    cold = time.perf_counter() - t
    pid1 = lz.runtime.pid
    time.sleep(9)
    gone = lz.runtime.pid is None
    free_idle = O.system_free_percent()
    t = time.perf_counter()
    d2 = lb.decide(reqs[0][1])
    restart = time.perf_counter() - t
    out["lazy_lifecycle"] = {"idle_exit_seconds": 6, "first_decision_s": round(cold, 2), "process_exited_when_idle": gone,
                             "system_free_percent_while_idle": free_idle, "restart_decision_s": round(restart, 2),
                             "same_decision_after_restart": (d1.answer("worker").choice, d1.answer("worker").confidence.value)
                             == (d2.answer("worker").choice, d2.answer("worker").confidence.value)}
finally:
    lz.close()
out["free_percent_after"] = O.system_free_percent()
if OUT.exists():
    raise RuntimeError("refusing to overwrite")
OUT.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: v for k, v in out.items() if k not in ("memory_after_first", "memory_after_warm", "memory_final")}, indent=1))
