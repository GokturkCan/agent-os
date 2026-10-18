"""Frozen-final report for the Open-Jev study (R3.2H): reads recorded results only (no inference). Writes audit/openjev-v3/report.json."""
import collections
import json
from pathlib import Path

import analyse as A
from agentos import systemone_calibration as K
from agentos import systemone_gates as G

ROOT = A.ROOT
cases = A.cases_of("final")
LAYA_BENCH = json.loads(Path("audit/systemone-eval-r3.2g/performance/A-bench.json").read_text())
OJ_BENCH = json.loads((ROOT / "bench.json").read_text())
oj_mem_gib = round(float(OJ_BENCH["memory_final"]["footprint_peak"].split()[0]) / 1024, 2)
SYSTEMS = ["label-prior", "first", "last", "random", "null", "det", "laya", "base", "base+pf", "alias", "alias+pf"]
NAMES = {"base": "Open-Jev baseline (shipped)", "alias": "Open-Jev optimised scoring (alias)", "base+pf": "Open-Jev + deterministic prefilter",
         "alias+pf": "Optimised hybrid (alias + prefilter)  [SELECTED]", "det": "Deterministic prefilter + policy order", "laya": "Laya-MLX (existing baseline)"}
out = {"partition": "final", "families": len({A.fam(c) for c in cases}), "cases": len(cases), "systems": {}}
res = {s: A.load("final", s) for s in SYSTEMS}
lp_bare = res["label-prior"]["variants"]["bare"]["layer1_decision_quality"]["acceptable_rate"]
out["label_prior_acceptable_bare"] = lp_bare
model_systems = ("base", "base+pf", "alias", "alias+pf")


def variant_recs(r, s, v):
    return A.recs_of(r, "bare" if s in ("label-prior", "first", "last", "random") else v)


for s in SYSTEMS:
    r = res[s]
    recs = variant_recs(r, s, "described")
    st = A.stats(recs, cases)
    row = {"name": NAMES.get(s, s), "acceptable": st["acceptable"], "acceptable_ci95": A.boot(recs, cases, A.acc_metric),
           "forbidden": st["forbidden"], "wrong_allowed": st["wrong_allowed"], "escalated": st["escalated"], "counter_prior": st["counter_prior"],
           "counter_prior_ci95": A.boot(recs, cases, lambda x, c: A.stats(x, c)["counter_prior"]),
           "utility": st["utility_per_decision"], "utility_ci95": A.boot(recs, cases, A.util_metric), "order_consistent": A.order_consistency(recs, cases),
           "real_labels_acceptable": A.stats([x for x in recs if "-real" in x["case"]], cases)["acceptable"],
           "misleading_labels_acceptable": A.stats([x for x in recs if "-misleading" in x["case"]], cases)["acceptable"],
           "en": A.stats([x for x in recs if "-en-" in x["case"]], cases)["acceptable"], "tr": A.stats([x for x in recs if "-tr-" in x["case"]], cases)["acceptable"]}
    ab = A.recs_of(r, "described+abstain") if "described+abstain" in r["variants"] else []
    if ab:
        sa = A.stats(ab, cases)
        row["with_abstain"] = {"acceptable": sa["acceptable"], "forbidden": sa["forbidden"], "escalated_on_answerable": sa["escalated"],
                               "esc_gold_correct": sa["esc_gold_correct"], "esc_gold_unsafe": sa["esc_gold_unsafe"], "utility": sa["utility_per_decision"],
                               "probe": (r.get("probes") or {}).get("abstention")}
    row["follows_label_swap_all"] = ((r.get("probes") or {}).get("description_swap_all") or {}).get("follows_label")
    if s in model_systems + ("laya", "det"):
        bench = OJ_BENCH if s in model_systems else None
        if s in model_systems:
            b, mem = {"warm_latency_ms": {"p95": OJ_BENCH["warm_baseline_ms"]["p95"]}}, oj_mem_gib
        elif s == "laya":
            b, mem = LAYA_BENCH, 1.08
        else:
            b, mem = {"warm_latency_ms": {"p95": 0.1}}, 0.0
        g = G.gates(r, lp_bare, bench=b, memory_gib=mem)
        row["gates"] = {k: g[k]["status"] for k in ("G1", "G2", "G3", "G4", "G5", "G6", "G7")}
        row["gates_passed"] = g["passed"]
        row["gate_values"] = {k: g[k]["value"] for k in ("G2", "G3", "G4", "G5", "G7")}
    row["wall_s"] = r.get("wall_s")
    row["model_calls"] = (r.get("scorer") or {}).get("model_calls")
    out["systems"][s] = row

# policy-sensitive errors by category (described variant): forbidden choice + unsafe selection
pol = {}
for s in ("det", "laya", "base", "alias", "base+pf", "alias+pf"):
    c = collections.Counter()
    for x in variant_recs(res[s], s, "described"):
        if x["outcome"] in ("forbidden_choice", "unsafe_selection"):
            c[x["category"]] += 1
    pol[s] = dict(c)
out["policy_sensitive_errors_by_category"] = pol
cat = {}
for s in ("det", "laya", "base", "alias", "alias+pf"):
    by = collections.defaultdict(lambda: [0, 0])
    for x in variant_recs(res[s], s, "described"):
        by[x["category"]][0] += x["outcome"] in A.E.SUCCESS
        by[x["category"]][1] += 1
    cat[s] = {k: f"{v[0]}/{v[1]}" for k, v in sorted(by.items())}
out["success_by_category"] = cat
# paired family-bootstrap deltas
rec = {s: A.recs_of(res[s], "described") for s in ("det", "base", "alias", "base+pf", "alias+pf", "laya")}
out["paired_deltas"] = {f"{a} - {b}": {"acceptable": A.paired_delta(rec[a], rec[b], cases, A.acc_metric), "utility": A.paired_delta(rec[a], rec[b], cases, A.util_metric)}
                        for a, b in (("alias+pf", "det"), ("alias+pf", "base"), ("alias", "base"), ("base+pf", "det"), ("alias+pf", "base+pf"), ("base", "laya"), ("alias+pf", "laya"))}
# calibration on final: maps fitted on cal ONLY, for the same system
calib = {}
for s in model_systems:
    rc = A.recs_of(A.load("cal", s, True))
    pts = [(float(x["conf_value"]), 1 if x["outcome"] == "correct" else 0) for x in rc if not x["escalated"] and x["conf_value"] is not None]
    plat, iso = K.fit_platt(pts), K.fit_isotonic(pts)
    fr = [x for x in A.recs_of(res[s]) if not x["escalated"] and x["conf_value"] is not None]
    fp = [(float(x["conf_value"]), 1 if x["outcome"] == "correct" else 0) for x in fr]
    cal = {}
    for lab, m in (("raw", None), ("platt", plat), ("isotonic", iso)):
        rel = K.reliability([(K.apply_map(m, c) if m else c, y) for c, y in fp])
        cal[lab] = {"ece": rel["ece"], "brier": rel["brier"], "auroc": rel["auroc"]}
    cov = {}
    for q in (0.0, 0.25, 0.5, 0.75):
        cs = sorted(c for c, _ in fp)
        thr = cs[int(q * (len(cs) - 1))] if cs else 0
        kept = [(c, y) for c, y in fp if c >= thr]
        cov[f"top_{int((1 - q) * 100)}%_by_confidence"] = {"coverage": round(len(kept) / len(fp), 3), "selective_accuracy": round(sum(y for _, y in kept) / len(kept), 3)}
    calib[s] = {"answered": len(fp), "maps_fitted_on": "cal", "metrics": cal, "risk_coverage": cov}
out["calibration_final"] = calib
# POST-HOC sensitivity (NOT a replacement of the primary result): the gold of some dynamic_capability families contradicts their own option metadata
# (an acceptable worker is listed as missing the required capability). Found after the final run by the v2-style consistency check below.
from agentos import config as _C, systemone_options as _O
_cfg = _C.load()
BAD = set()
for _part in ("cal", "opt", "final"):
    for _cid, _c in A.cases_of(_part).items():
        _r, _g = _c["request"], _c["gold"]
        _info = {**_O.build(_cfg, _r["eligible_options"], _r["required_capabilities"]), **_r.get("option_info_extra", {})}
        if any(o in set(_g.get("acceptable", [])) and (x.get("missing") or x.get("status") == "unavailable" or (_r["state"].get("interactive") and x.get("interactive") is False))
               for o, x in _info.items()):
            BAD.add((_part, A.fam(_cid)))
out["gold_metadata_inconsistent_families"] = sorted(f"{p}:{f}" for p, f in BAD)
bad_final = {f for p, f in BAD if p == "final"}
sens = {}
for s in ("det", "laya", "base", "base+pf", "alias", "alias+pf"):
    rr = [x for x in A.recs_of(res[s]) if A.fam(x["case"]) not in bad_final]
    st = A.stats(rr, cases)
    sens[s] = {"acceptable": st["acceptable"], "ci95": A.boot(rr, cases, A.acc_metric), "forbidden": st["forbidden"], "escalated": st["escalated"], "utility": st["utility_per_decision"]}
out["final_excluding_inconsistent_families_POST_HOC"] = {"excluded_families": sorted(bad_final), **sens}
sel = json.loads((ROOT / "selection.json").read_text())
out["selection_frozen_before_final"] = {"selected": sel["selected"], "tau": sel["tau"]["adopted"]}
out["order_sensitivity_cal_opt"] = json.loads((ROOT / "order-sensitivity.json").read_text())
(ROOT / "report.json").write_text(json.dumps(out, indent=1) + "\n")
print(f"{'system':52} acc [ci95]            forb  cp    util   order  follows  real/mis  EN/TR       gates")
for s in SYSTEMS:
    r = out["systems"][s]
    print(f"{r['name'][:52]:52} {r['acceptable']:.3f} {r['acceptable_ci95']} {r['forbidden']:.3f} {r['counter_prior'] if r['counter_prior'] is None else round(r['counter_prior'], 3)} "
          f"{r['utility']:.3f} {r['order_consistent']} {r['follows_label_swap_all']} {r['real_labels_acceptable']:.2f}/{r['misleading_labels_acceptable']:.2f} "
          f"{r['en']:.2f}/{r['tr']:.2f} {r.get('gates_passed', '-')}")
