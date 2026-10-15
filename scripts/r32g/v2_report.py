"""Gate verdicts + comparison tables for the frozen v2 run. Reads audit/systemone-eval-r3.2g/v2/*.json and performance/*.
Memory for G6: the original gate's measure (peak sampled worker RSS) AND macOS physical footprint are both reported; the
gate is evaluated on the LARGER of the two so a GPU-heavy worker cannot pass on RSS alone."""
import collections, json
from pathlib import Path
from agentos import systemone_gates as G
root = Path("audit/systemone-eval-r3.2g"); v2 = root / "v2"
foot = {"A": 1.0, "C": 1575 / 1024, "D": 6527 / 1024}      # footprint GiB from performance/*-worker-footprint.txt (MB/1024)
bench = {"A": "A", "C": "B2-raw", "D": "D"}
prior = G.load(v2 / "label-prior.json")["variants"]["bare"]["layer1_decision_quality"]["acceptable_rate"]
out, f = {"label_prior_v2": prior, "systems": {}}, lambda v: "-" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
for n in ("A", "C", "D"):
    res = G.load(v2 / f"{n}.json"); b = G.load(root / "performance" / f"{bench[n]}-bench.json")
    rss = b["memory"]["worker_rss_mib_peak_sampled"] / 1024
    mem = max(rss, foot[n]) if n != "A" else max(rss, 1575 / 1024 * 0 + rss)
    row = G.row(n, res, prior, bench=b, memory_gib=mem)
    row["rss_gib"], row["footprint_gib"] = round(rss, 3), round(foot[n], 3) if n != "A" else None
    probes = res["probes"]; ab = probes.get("abstention") or {}
    row["abstention"] = {k: ab.get(k) for k in ("precision_of_abstention_on_escalate_gold", "recall_of_abstention_on_escalate_gold", "abstain_rate")}
    row["swap"] = {k: probes.get(k) for k in ("description_swap", "description_swap_all")}
    row["e2e"] = (res["layer3_end_to_end_routing"].get("passed"), res["layer3_end_to_end_routing"].get("cases"))
    row["warm_bench_ms"] = {k: b["warm_latency_ms"][k] for k in ("p50", "p95", "p99")}
    row["cold_s"] = b["cold_start"]["spawn_to_ready_s"]; row["calls"] = (res.get("pipeline") or {}).get("model_calls_per_decision_mean") or 1.0
    cat = collections.defaultdict(lambda: [0, 0])
    for r in res["records"]:
        if r["variant"] == "described" and r["kind"] == "semantic":
            cat[r["category"]][0] += r["outcome"] == "correct"; cat[r["category"]][1] += 1
    row["by_category"] = {k: round(a / t, 3) for k, (a, t) in sorted(cat.items())}
    out["systems"][n] = row
for n in ("first", "last", "label-prior", "random", "Null"):
    r = G.load(v2 / f"{n}.json"); d = r["variants"]["bare"]["layer1_decision_quality"]
    out["systems"][n] = {"acceptable": d["acceptable_rate"], "escalated": d["escalation_rate"], "forbidden": d["forbidden_choice_rate"]}
(root / "v2-report.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
print(f"v2 label-prior = {prior}")
print("sys  acc    EN     TR     forb   cprior order  esc    swapFL absPrec absRec accAb  escG   p50bench p95bench cold  rss    foot  calls  gates")
for n in ("A", "C", "D"):
    s = out["systems"][n]; g = s["gates"]
    print(f"{n:3} {f(s['acceptable']):>6} {f(s['en']):>6} {f(s['tr']):>6} {f(s['forbidden']):>6} {f(s['counter_prior']):>6} {f(s['order_consistent']):>6} {f(s['escalated']):>6} {f(g['G2']['value']):>6} "
          f"{f(s['abstention']['precision_of_abstention_on_escalate_gold']):>6} {f(s['abstention']['recall_of_abstention_on_escalate_gold']):>6} {f(s['acceptable_with_abstain']):>6} {f(s['esc_gold_with_abstain']):>6} "
          f"{s['warm_bench_ms']['p50']:>8} {s['warm_bench_ms']['p95']:>8} {s['cold_s']:>5} {s['rss_gib']:>6} {f(s['footprint_gib']):>5} {s['calls']:>5}  {g['passed']}/7 unknown={g['unknown']} " + " ".join(f"{k}={g[k]['status']}" for k in ('G1','G2','G3','G4','G5','G6','G7')) + f"  e2e={s['e2e']}")
for n in ("first", "last", "label-prior", "random", "Null"):
    s = out["systems"][n]; print(f"{n:12} acc={f(s['acceptable'])} esc={f(s['escalated'])} forb={f(s['forbidden'])}")
for n in ("A", "C", "D"):
    print(n, out["systems"][n]["by_category"])
