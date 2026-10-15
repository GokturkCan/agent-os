"""G1–G7 (Phase 2A §6, unchanged) computed from `agentos systemone-eval` results (R3.2G reporting helper).

G1 protocol compliance >= 0.99 in every variant and no uncontained exception
G2 description-swap-all follows-label <= 0.60                       (failing G2 or G3 is a NO-GO)
G3 counter-prior acceptable (described) >= 0.60
G4 order consistency (described) >= 0.80
G5 acceptable (described) - label-prior baseline acceptable >= +0.05 (baseline measured on the SAME dataset)
G6 warm p95 <= 1000 ms and memory <= 7 GiB (from a bench result when given; otherwise the eval's described p95, marked)
G7 abstention precision >= 0.5 when abstention is exposed
"""
from __future__ import annotations

import json
from pathlib import Path


def _l1(res, v="described"):
    return res["variants"][v]["layer1_decision_quality"]


def _number(value):
    import math
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _gate(value, passed, **extra):
    return {"value": value, "pass": passed,
            "status": "UNKNOWN" if passed is None else ("PASS" if passed else "FAIL"), **extra}


def gates(res: dict, label_prior: float | None, bench: dict | None = None, memory_gib: float | None = None) -> dict:
    """Missing measurements are UNKNOWN. A measured failure remains FAIL.

    G6 requires the warm benchmark AND a memory measurement, not screening eval
    latency. G7 consumes the evaluator's canonical abstention key only; unknown
    schemas are not silently interpreted as zero abstentions or a passing gate.
    """
    out = {}
    variants = res.get("variants") or {}
    comp = [(v.get("layer2_protocol_compliance") or {}).get("compliance_rate") for v in variants.values()]
    records = res.get("records")
    exc = any(any("exception" in v for v in r.get("protocol_violations", [])) for r in (records or []))
    measured = [v for v in comp if _number(v)]
    complete = bool(comp) and len(measured) == len(comp) and isinstance(records, list) and bool(records)
    p = False if exc or any(v < .99 for v in measured) else (True if complete else None)
    out["G1"] = _gate(min(measured) if measured else None, p)
    probes = res.get("probes") or {}
    fl = (probes.get("description_swap_all") or {}).get("follows_label")
    out["G2"] = _gate(fl, fl <= .60 if _number(fl) else None)
    d = (variants.get("described") or {}).get("layer1_decision_quality") or {}
    cp = (d.get("counter_prior") or {}).get("acceptable_rate")
    out["G3"] = _gate(cp, cp >= .60 if _number(cp) else None)
    oc = (d.get("order_robustness") or {}).get("choice_consistent_across_orders")
    out["G4"] = _gate(oc, oc >= .80 if _number(oc) else None)
    acc = d.get("acceptable_rate")
    delta = acc - label_prior if _number(acc) and _number(label_prior) else None
    out["G5"] = _gate(round(delta, 4) if delta is not None else None, delta >= .05 if delta is not None else None)
    p95 = ((bench or {}).get("warm_latency_ms") or {}).get("p95")
    fail = (_number(p95) and p95 > 1000) or (_number(memory_gib) and memory_gib > 7)
    known = _number(p95) and _number(memory_gib)
    out["G6"] = _gate({"p95_ms": p95, "memory_gib": memory_gib, "source": "bench" if bench else "missing",
                       "eval_screening_p95_ms": ((variants.get("described") or {}).get("operational", {}).get("latency_ms") or {}).get("p95")},
                      False if fail else (True if known else None))
    prec = (probes.get("abstention") or {}).get("precision_of_abstention_on_escalate_gold")
    out["G7"] = _gate(prec, prec >= .5 if _number(prec) else None)
    names = [f"G{i}" for i in range(1, 8)]
    out["passed"] = sum(out[g]["pass"] is True for g in names)
    out["unknown"] = [g for g in names if out[g]["pass"] is None]
    out["no_go_gate_failed"] = any(out[g]["pass"] is False for g in ("G2", "G3"))
    out["all_pass"] = out["passed"] == 7
    return out


def row(name: str, res: dict, label_prior: float, **kw) -> dict:
    d = _l1(res)
    da = _l1(res, "described+abstain") if "described+abstain" in res["variants"] else None
    by = d.get("by_language") or d.get("by_lang") or {}
    return {"name": name, "acceptable": d["acceptable_rate"], "forbidden": d["forbidden_choice_rate"],
            "counter_prior": d["counter_prior"]["acceptable_rate"],
            "order_consistent": d["order_robustness"]["choice_consistent_across_orders"],
            "escalated": d["escalation_rate"], "answered_precision": d["answered_precision"],
            "en": (by.get("en") or {}).get("acceptable_rate"), "tr": (by.get("tr") or {}).get("acceptable_rate"),
            "esc_gold_with_abstain": da["escalation_gold"]["escalation_correctness"] if da else None,
            "acceptable_with_abstain": da["acceptable_rate"] if da else None,
            "p50_ms": res["variants"]["described"]["operational"]["latency_ms"].get("p50"),
            "p95_ms": res["variants"]["described"]["operational"]["latency_ms"].get("p95"),
            "calls_per_decision": (res.get("pipeline") or {}).get("model_calls_per_decision_mean"),
            "gates": gates(res, label_prior, **kw)}


def load(path) -> dict:
    return json.loads(Path(path).read_text())
