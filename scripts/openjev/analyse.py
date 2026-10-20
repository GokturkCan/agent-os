"""Offline analysis of recorded Open-Jev study results (R3.2H). No inference. Family-level uncertainty, calibration, abstention trade-offs.

  uv run python scripts/openjev/analyse.py table <part> <sys,sys,...> [--light]
  uv run python scripts/openjev/analyse.py select          # choose policy/tau on cal+opt only, write audit/openjev-v3/selection.json
Utility (declared before looking at final): correct +1, wrong-but-allowed -1, forbidden -3, escalated on answerable 0, correct escalation +1,
unsafe selection (picked a worker where gold says escalate) -3.
"""
import collections
import json
import random
import sys
from pathlib import Path

from agentos import systemone_calibration as K
from agentos import systemone_eval as E

ROOT = Path("audit/openjev-v3")
DATA = {"dev": E.DATASET, "cal": Path("evals/data/openjev-v3-cal.yaml"), "opt": Path("evals/data/openjev-v3-opt.yaml"),
        "final": Path("evals/data/openjev-v3-final.yaml")}
UTIL = {"correct": 1, "wrong_allowed": -1, "forbidden_choice": -3, "escalated": 0, "correct_escalation": 1, "unsafe_selection": -3,
        "escalated_wrong_reason": 0, "protocol_violation": -3}
fam = lambda cid: cid.rsplit("-", 2)[0]


class IntegrityError(RuntimeError):
    """A recorded result does not match the frozen dataset/partition it claims to measure: refuse to analyse it (fail closed)."""


def _frozen_sha(part):
    return json.loads((ROOT / "freeze.json").read_text())["files"].get(f"evals/data/openjev-v3-{part}.yaml")


def verify(part, name, res):
    """Fail closed on a result file that is not a complete measurement of its (frozen) partition."""
    frozen = _frozen_sha(part)                                    # None for the pre-existing dev set (not part of the v3 freeze)
    if frozen is not None and (res.get("dataset") or {}).get("sha256") != frozen:
        raise IntegrityError(f"{part}/{name}: dataset sha256 does not match audit/openjev-v3/freeze.json")
    ids = set(cases_of(part))
    for v in {r["variant"] for r in res["records"]}:
        got = {r["case"] for r in res["records"] if r["variant"] == v and r["kind"] == "semantic"}
        if not got or not got <= ids:
            raise IntegrityError(f"{part}/{name}/{v}: records are empty or reference cases outside the partition")
    sets = {frozenset(r["case"] for r in res["records"] if r["variant"] == v and r["kind"] == "semantic")
            for v in {r["variant"] for r in res["records"]}}
    if len(sets) != 1:
        raise IntegrityError(f"{part}/{name}: variants do not cover the same cases (incomplete run)")
    bad = {r["outcome"] for r in res["records"]} - set(UTIL)
    if bad:
        raise IntegrityError(f"{part}/{name}: unknown outcome(s) {sorted(bad)} would be silently scored 0")


def load(part, name, light=False):
    """Recorded result or None when the file does not exist; an existing file must pass verify()."""
    p = ROOT / part / f"{name}{'-light' if light else ''}.json"
    if not p.exists():
        return None
    res = json.loads(p.read_text())
    verify(part, name, res)
    return res


def cases_of(part):
    return {c["id"]: c for c in E.load_dataset(DATA[part])["cases"]}


def recs_of(res, variant="described"):
    return [r for r in res["records"] if r["variant"] == variant and r["kind"] == "semantic"]


def stats(recs, cases):
    ans = [r for r in recs if not cases[r["case"]]["gold"].get("escalate")]
    esc = [r for r in recs if cases[r["case"]]["gold"].get("escalate")]
    c = collections.Counter(r["outcome"] for r in ans)
    cp = [r for r in ans if "claude_code" not in cases[r["case"]]["gold"]["acceptable"]]
    n = len(ans) or 1
    return {"n": len(recs), "answerable": len(ans), "acceptable": round(c["correct"] / n, 4), "forbidden": round(c["forbidden_choice"] / n, 4),
            "wrong_allowed": round(c["wrong_allowed"] / n, 4), "escalated": round(c["escalated"] / n, 4),
            "counter_prior": round(sum(r["outcome"] == "correct" for r in cp) / len(cp), 4) if cp else None,
            "esc_gold_correct": round(sum(r["outcome"] == "correct_escalation" for r in esc) / len(esc), 4) if esc else None,
            "esc_gold_unsafe": round(sum(r["outcome"] == "unsafe_selection" for r in esc) / len(esc), 4) if esc else None,
            "utility_per_decision": round(sum(UTIL[r["outcome"]] for r in recs) / len(recs), 4) if recs else None}


def order_consistency(recs, cases):
    per = collections.defaultdict(list)
    for r in recs:
        if not cases[r["case"]]["gold"].get("escalate") and len(cases[r["case"]]["request"]["eligible_options"]) >= 2:
            per[r["case"]].append(r)
    ok = sum(1 for rs in per.values() if not any(x["escalated"] for x in rs) and len({x["choice"] for x in rs}) == 1)
    return round(ok / len(per), 4) if per else None


def boot(recs, cases, metric, n=2000, seed=1337):
    byf = collections.defaultdict(list)
    for r in recs:
        byf[fam(r["case"])].append(r)
    fams = sorted(byf)
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        pick = [x for f in (rng.choice(fams) for _ in fams) for x in byf[f]]
        v = metric(pick, cases)
        if v is not None:
            vals.append(v)
    vals.sort()
    return [round(vals[int(.025 * (len(vals) - 1))], 3), round(vals[int(.975 * (len(vals) - 1))], 3)] if vals else None


def paired_delta(ra, rb, cases, metric, n=2000, seed=1337):
    """Cluster-bootstrap CI of metric(A) - metric(B) over the SAME resampled families."""
    ba, bb = collections.defaultdict(list), collections.defaultdict(list)
    for r in ra:
        ba[fam(r["case"])].append(r)
    for r in rb:
        bb[fam(r["case"])].append(r)
    fams = sorted(set(ba) & set(bb))
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        pick = [rng.choice(fams) for _ in fams]
        a = metric([x for f in pick for x in ba[f]], cases)
        b = metric([x for f in pick for x in bb[f]], cases)
        if a is not None and b is not None:
            d.append(a - b)
    d.sort()
    return {"delta": round(metric(ra, cases) - metric(rb, cases), 4), "ci95": [round(d[int(.025 * (len(d) - 1))], 3), round(d[int(.975 * (len(d) - 1))], 3)],
            "share_gt0": round(sum(x > 0 for x in d) / len(d), 3)}


acc_metric = lambda recs, cases: stats(recs, cases)["acceptable"]
util_metric = lambda recs, cases: stats(recs, cases)["utility_per_decision"]


def apply_tau(recs, cases, tau, cal=None):
    """Re-decide records offline: an answered decision whose (calibrated) confidence is below tau becomes an escalation."""
    out = []
    for r in recs:
        if r["escalated"] or r["conf_value"] is None:
            out.append(r)
            continue
        c = K.apply_map(cal, r["conf_value"]) if cal else r["conf_value"]
        if c < tau:
            gold_esc = cases[r["case"]]["gold"].get("escalate")
            out.append({**r, "escalated": True, "choice": None, "outcome": "correct_escalation" if gold_esc else "escalated"})
        else:
            out.append(r)
    return out


def reliability(recs):
    return K.reliability([(float(r["conf_value"]), 1 if r["outcome"] == "correct" else 0) for r in recs
                          if not r["escalated"] and r["conf_value"] is not None])


def table(part, names, light):
    cases = cases_of(part)
    for n in names.split(","):
        res = load(part, n, light)
        if not res:
            print(n, "MISSING")
            continue
        recs = recs_of(res)
        s = stats(recs, cases)
        print(f"{n:12} acc {s['acceptable']:.3f} {boot(recs, cases, acc_metric)} forb {s['forbidden']:.3f} cp {s['counter_prior']} esc {s['escalated']:.3f} "
              f"order {order_consistency(recs, cases)} util {s['utility_per_decision']} ece {reliability(recs).get('ece')}")


if __name__ == "__main__":
    if sys.argv[1] == "table":
        table(sys.argv[2], sys.argv[3], "--light" in sys.argv)


def select():
    """Pre-declared rule, evaluated on cal+opt ONLY: highest mean utility per decision (pooled over both partitions); ties -> fewer model calls
    (canon/base 1, alias 1, ens 2), then simpler. tau: argmax calibration-partition utility on a 0.05 grid under the Platt map fitted on cal;
    adopted only if it improves the pooled utility on opt over no-tau, otherwise tau=None."""
    out = {"rule": select.__doc__.strip(), "candidates": {}}
    cc, co = cases_of("cal"), cases_of("opt")
    calls = {"base": 1, "canon": 1, "alias": 1, "ens": 2}
    for name in ("base", "canon", "alias", "ens", "base+pf", "alias+pf", "ens+pf"):
        rc, ro = recs_of(load("cal", name, True)), recs_of(load("opt", name, True))
        sc, so = stats(rc, cc), stats(ro, co)
        pooled = round((sc["utility_per_decision"] * len(rc) + so["utility_per_decision"] * len(ro)) / (len(rc) + len(ro)), 4)
        out["candidates"][name] = {"cal": sc, "opt": so, "pooled_utility": pooled, "model_calls_per_decision": calls[name.split("+")[0]]}
    best = max(out["candidates"], key=lambda n: (out["candidates"][n]["pooled_utility"], -out["candidates"][n]["model_calls_per_decision"], -len(n)))
    out["selected"] = best
    rc, ro = recs_of(load("cal", best, True)), recs_of(load("opt", best, True))
    pts = [(float(r["conf_value"]), 1 if r["outcome"] == "correct" else 0) for r in rc if not r["escalated"] and r["conf_value"] is not None]
    plat, iso = K.fit_platt(pts), K.fit_isotonic(pts)
    grid = [x / 20 for x in range(0, 20)]
    cal_u = {t: stats(apply_tau(rc, cc, t, plat), cc)["utility_per_decision"] for t in grid}
    tau = min(t for t in grid if cal_u[t] == max(cal_u.values()))
    opt_base, opt_tau = stats(ro, co)["utility_per_decision"], stats(apply_tau(ro, co, tau, plat), co)["utility_per_decision"]
    out["tau"] = {"cal_argmax": tau, "opt_utility_without": opt_base, "opt_utility_with": opt_tau, "adopted": None if opt_tau <= opt_base else tau,
                  "grid_cal_utility": cal_u}
    out["calibration_maps_fit_on_cal"] = {"platt": plat, "isotonic": {"x": iso["x"], "y": iso["y"]}}
    Path(ROOT / "selection.json").write_text(json.dumps(out, indent=1) + "\n")
    print("selected", best, "tau", out["tau"]["adopted"], {n: c["pooled_utility"] for n, c in out["candidates"].items()})


if __name__ == "__main__" and sys.argv[1] == "select":
    select()
