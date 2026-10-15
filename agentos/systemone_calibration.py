"""Offline confidence analysis for SystemOne evaluation results (R3.2G). ANALYSIS ONLY.

  agentos systemone-calibration --fit DEV.json [--apply OTHER.json ...] [--variant described] [--out result.json]

Reads the per-decision records written by `agentos systemone-eval --out` and measures how the backend's RAW top-choice
confidence relates to being correct: reliability bins, ECE (equal-width bins), Brier score, AUROC (does higher confidence
separate right from wrong?) and the coverage-vs-accuracy curve (answer only the most confident x%).
Isotonic (pool-adjacent-violators) and Platt maps are FITTED ON THE --fit FILE ONLY and applied unchanged to --apply files.

Nothing here changes runtime behaviour: no threshold is activated, and no confidence is ever relabelled
`kind="calibrated"`. Calibration can make a score honest about its own accuracy; it cannot fix label bias or a wrong
decision (an option-order or label-following failure is still a failure at any confidence).
"""
from __future__ import annotations

import bisect
import json
import math
from pathlib import Path

BINS = 10


def points(result: dict, variant: str) -> list[tuple[float, int]]:
    """(raw confidence, correct?) for every ANSWERED decision of `variant` that carried a raw confidence."""
    out = []
    for r in result.get("records", []):
        if r.get("variant") != variant or r.get("escalated") or r.get("conf_kind") != "raw" or r.get("conf_value") is None:
            continue
        out.append((float(r["conf_value"]), 1 if r.get("outcome") == "correct" else 0))
    return out


def reliability(ps: list[tuple[float, int]], bins: int = BINS) -> dict:
    if not ps:
        return {"n": 0}
    rows, ece = [], 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, y) for c, y in ps if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if not sel:
            continue
        conf = sum(c for c, _ in sel) / len(sel)
        acc = sum(y for _, y in sel) / len(sel)
        ece += len(sel) / len(ps) * abs(acc - conf)
        rows.append({"bin": [round(lo, 2), round(hi, 2)], "n": len(sel), "mean_conf": round(conf, 4), "accuracy": round(acc, 4)})
    n = len(ps)
    acc = sum(y for _, y in ps) / n
    return {"n": n, "accuracy": round(acc, 4), "mean_conf": round(sum(c for c, _ in ps) / n, 4),
            "ece": round(ece, 4), "brier": round(sum((c - y) ** 2 for c, y in ps) / n, 4), "auroc": auroc(ps),
            "bins": rows, "coverage_accuracy": coverage_curve(ps)}


def auroc(ps: list[tuple[float, int]]):
    pos = [c for c, y in ps if y]
    neg = [c for c, y in ps if not y]
    if not pos or not neg:
        return None
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def coverage_curve(ps: list[tuple[float, int]], steps=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)) -> list[dict]:
    s = sorted(ps, key=lambda p: -p[0])
    out = []
    for cov in steps:
        k = max(1, round(cov * len(s)))
        top = s[:k]
        out.append({"coverage": cov, "n": k, "min_conf": round(top[-1][0], 4), "accuracy": round(sum(y for _, y in top) / k, 4)})
    return out


# ------------------------------------------------------------ calibration maps (fit on one set, apply to another)
def fit_isotonic(ps: list[tuple[float, int]]) -> dict:
    """Pool-adjacent-violators on confidence-sorted points -> non-decreasing step function."""
    groups: dict[float, list] = {}                # tied confidences form one point (else PAV splits them)
    for c, y in ps:
        g = groups.setdefault(c, [0.0, 0])
        g[0] += y
        g[1] += 1
    blocks = []                                   # [sum_y, count, max_x]
    for c in sorted(groups):
        blocks.append([groups[c][0], groups[c][1], c])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            y2, n2, x2 = blocks.pop()
            blocks[-1][0] += y2
            blocks[-1][1] += n2
            blocks[-1][2] = x2
    return {"kind": "isotonic", "x": [b[2] for b in blocks], "y": [round(b[0] / b[1], 6) for b in blocks]}


def _logit(c: float) -> float:
    c = min(max(c, 1e-6), 1 - 1e-6)
    return math.log(c / (1 - c))


def _sigmoid(z: float) -> float:
    # Both branches exponentiate a non-positive number, including extreme logits.
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def fit_platt(ps: list[tuple[float, int]], iters: int = 200) -> dict:
    """Damped Newton fit with backtracking on stable logistic loss (offline only).

    A tiny ridge makes constant-confidence and separated samples well-defined.
    Backtracking prevents the unconstrained Newton overshoot seen in R3.2G run 1.
    """
    if not ps:
        return {"kind": "platt", "a": 1.0, "b": 0.0}
    xy = [(_logit(c), y) for c, y in ps]
    ridge = 1e-6
    a, b = 1.0, 0.0

    def loss(a, b):
        return sum(max(a*x+b, 0) - y*(a*x+b) + math.log1p(math.exp(-abs(a*x+b)))
                   for x, y in xy) + ridge * (a*a + b*b) / 2

    for _ in range(iters):
        ga, gb, haa, hab, hbb = ridge*a, ridge*b, ridge, 0.0, ridge
        for x, y in xy:
            p = _sigmoid(a*x+b)
            w = p * (1-p)
            ga += (p-y)*x
            gb += p-y
            haa += w*x*x
            hab += w*x
            hbb += w
        det = haa*hbb - hab*hab
        if det <= 0 or not math.isfinite(det):
            break
        da, db = (hbb*ga-hab*gb)/det, (haa*gb-hab*ga)/det
        scale, old = 1.0, loss(a, b)
        while scale > 1e-12:
            na, nb = a-scale*da, b-scale*db
            if math.isfinite(na) and math.isfinite(nb) and loss(na, nb) <= old:
                break
            scale *= 0.5
        if scale <= 1e-12:
            break
        a, b = na, nb
        if scale*(abs(da)+abs(db)) < 1e-9:
            break
    return {"kind": "platt", "a": a, "b": b, "ridge": ridge}


def apply_map(m: dict, c: float) -> float:
    if m["kind"] == "isotonic":
        if not m["x"]:
            return c
        i = bisect.bisect_left(m["x"], c)
        return m["y"][min(i, len(m["y"]) - 1)]
    return _sigmoid(m["a"] * _logit(c) + m["b"])


def analyse(fit: dict, applies: dict[str, dict], variant: str) -> dict:
    fit_ps = points(fit, variant)
    out = {"variant": variant, "note": "RAW confidence analysis; maps fitted on the fit set only; nothing is activated",
           "fit": {"backend": fit.get("backend"), "dataset": (fit.get("dataset") or {}).get("id"), "raw": reliability(fit_ps)}}
    if len(fit_ps) < 20 or len({y for _, y in fit_ps}) < 2:
        out["maps"] = None
        out["maps_note"] = "too few answered decisions (or one class only) to fit a map"
        maps = {}
    else:
        maps = {"isotonic": fit_isotonic(fit_ps), "platt": fit_platt(fit_ps)}
        out["maps"] = maps
    out["applied"] = {}
    for label, res in applies.items():
        ps = points(res, variant)
        entry = {"backend": res.get("backend"), "dataset": (res.get("dataset") or {}).get("id"), "raw": reliability(ps)}
        for k, m in maps.items():
            entry[k] = reliability([(apply_map(m, c), y) for c, y in ps])
        out["applied"][label] = entry
    return out


def add_parser(sub) -> None:
    sp = sub.add_parser("systemone-calibration", help="offline raw-confidence / calibration analysis of eval results")
    sp.add_argument("--fit", required=True, help="systemone-eval result JSON used to fit maps (development data)")
    sp.add_argument("--apply", nargs="*", default=[], help="result JSONs the fitted maps are applied to, unchanged")
    sp.add_argument("--variant", default="described")
    sp.add_argument("--out")


def run(cfg, a) -> int:
    fit = json.loads(Path(a.fit).read_text())
    applies = {p: json.loads(Path(p).read_text()) for p in a.apply}
    res = analyse(fit, applies, a.variant)
    text = json.dumps(res, indent=2)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n")
    f = res["fit"]["raw"]
    print(f"fit {res['fit']['backend']} {a.variant}: n={f.get('n')} acc={f.get('accuracy')} conf={f.get('mean_conf')} "
          f"ECE={f.get('ece')} Brier={f.get('brier')} AUROC={f.get('auroc')}")
    for label, e in res["applied"].items():
        r = e["raw"]
        line = f"apply {label}: n={r.get('n')} raw ECE={r.get('ece')} AUROC={r.get('auroc')}"
        for k in ("isotonic", "platt"):
            if k in e:
                line += f" | {k} ECE={e[k].get('ece')}"
        print(line)
    return 0
