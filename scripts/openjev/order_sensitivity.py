"""Numeric option-order sensitivity of the shipped Open-Jev scoring, from the recorded score cache (no inference, offline client)."""
import itertools
import json
import sys
from pathlib import Path

from agentos import config as C, systemone_eval as E
import openjev_opt as O

cfg = C.load()
client = O.ScoreClient(cfg, cache_path="state/openjev-opt/cache.jsonl", offline=True)
res = {}
for part in sys.argv[1:]:
    data = E.load_dataset(Path(f"evals/data/openjev-v3-{part}.yaml"))
    diffs, flips, ties, n, missing = [], 0, 0, 0, 0
    for c in data["cases"]:
        opts = c["request"]["eligible_options"]
        if len(opts) < 2:
            continue
        for variant in ("bare", "described", "described+abstain"):
            per = []
            for order in itertools.permutations(opts):
                be = O.OpenJevBackend(client, "baseline")
                try:
                    be.decide(E.build_request(cfg, c, order, variant))
                except KeyError:
                    missing += 1
                    per = []
                    break
                per.append(dict(zip(be.trace[-1]["keys"], be.trace[-1]["probs"])))
            if len(per) < 2:
                continue
            n += 1
            keys = per[0].keys()
            diffs.append(max(abs(a[k] - b[k]) for a, b in itertools.combinations(per, 2) for k in keys))
            top = {max(p, key=p.get) for p in per}
            flips += len(top) > 1
            ties += any(sorted(p.values())[-1] - sorted(p.values())[-2] < 1e-6 for p in per)
    diffs.sort()
    res[part] = {"request_sets": n, "missing_from_cache": missing, "max_abs_prob_diff_across_orders": {"max": diffs[-1] if diffs else None, "p95": diffs[int(.95 * (len(diffs) - 1))] if diffs else None, "mean": sum(diffs) / len(diffs) if diffs else None},
                 "argmax_flips_across_orders": flips, "near_ties_lt_1e-6": ties}
print(json.dumps(res, indent=1))
Path("audit/openjev-v3/order-sensitivity.json").write_text(json.dumps(res, indent=1) + "\n")
