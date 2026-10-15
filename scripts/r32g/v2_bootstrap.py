"""POST-HOC descriptive uncertainty on frozen v2 results: cluster bootstrap over the 32 scenario families (a family =
the id prefix v2-NN; its en/tr x real/misleading variants are related observations, not independent tasks).
Does not change any gate verdict; it only shows how stable the margins are."""
import json, random, collections
from pathlib import Path
from agentos import systemone_eval as E
root = Path("audit/systemone-eval-r3.2g"); data = E.load_dataset(Path("evals/data/systemone-heldout-v2.yaml"))
cases = {c["id"]: c for c in data["cases"]}; fam = lambda cid: cid.rsplit("-", 2)[0]
lp = json.load(open(root / "v2/label-prior.json"))["records"]
def stats(recs, ids):
    r = [x for x in recs if x["variant"] == "described" and x["kind"] == "semantic" and fam(x["case"]) in ids]
    ans = [x for x in r if not cases[x["case"]]["gold"].get("escalate")]
    acc = sum(x["outcome"] == "correct" for x in r) / len(r)
    cp = [x for x in ans if "claude_code" not in cases[x["case"]]["gold"]["acceptable"]]
    byc = collections.defaultdict(set)
    for x in ans: byc[x["case"]].add(x["choice"])
    return acc, (sum(x["outcome"] == "correct" for x in cp) / len(cp) if cp else None)
out = {}
for n in ("A", "C", "D"):
    recs = json.load(open(root / f"v2/{n}.json"))["records"]
    base_ids = sorted({fam(x["case"]) for x in recs}); rng = random.Random(1337); samples = []
    by_fam = {f: [x for x in recs if fam(x["case"]) == f] for f in base_ids}; lp_fam = {f: [x for x in lp if fam(x["case"]) == f] for f in base_ids}
    for _ in range(2000):
        pick = [rng.choice(base_ids) for _ in base_ids]
        rr = [x for f in pick for x in by_fam[f] if x["variant"] == "described" and x["kind"] == "semantic"]
        lr = [x for f in pick for x in lp_fam[f] if x["variant"] == "bare" and x["kind"] == "semantic"]
        acc = sum(x["outcome"] == "correct" for x in rr) / len(rr); pri = sum(x["outcome"] == "correct" for x in lr) / len(lr)
        cp = [x for x in rr if not cases[x["case"]]["gold"].get("escalate") and "claude_code" not in cases[x["case"]]["gold"]["acceptable"]]
        samples.append((acc, acc - pri, sum(x["outcome"] == "correct" for x in cp) / len(cp) if cp else None))
    q = lambda xs, p: round(sorted(xs)[int(p * (len(xs) - 1))], 3)
    col = lambda i: [s[i] for s in samples if s[i] is not None]
    out[n] = {"families": len(base_ids), "acceptable_ci95": [q(col(0), .025), q(col(0), .975)], "G5_delta_ci95": [q(col(1), .025), q(col(1), .975)],
              "G5_delta_gt_0.05_share": round(sum(s[1] >= .05 for s in samples) / len(samples), 3),
              "G3_counter_prior_ci95": [q(col(2), .025), q(col(2), .975)], "G3_ge_0.60_share": round(sum(s[2] >= .6 for s in col_ if True) / len(col(2)), 3) if (col_ := samples) else None}
(root / "v2-bootstrap.json").write_text(json.dumps(out, indent=1) + "\n"); print(json.dumps(out, indent=1))
