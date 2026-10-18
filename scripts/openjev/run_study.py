"""Sequential Open-Jev study runner (R3.2H). One model process, one shared payload cache, refuses to overwrite evidence.

  uv run python scripts/openjev/run_study.py <dataset-key> <system>[,<system>...]
dataset-key: dev | heldout-v1 | v2 | cal | opt | final   (v3 partitions are evals/data/openjev-v3-<part>.yaml)
systems: base | canon | alias | ens | det | base+pf | canon+pf | ens+pf | laya | null | first | last | label-prior | random
(tau / calibrated variants are applied offline by scripts/openjev/analyse.py from the recorded confidences)
"""
import json
import sys
import time
from pathlib import Path

from agentos import config as C, systemone_adapter as A, systemone_eval as E
from agentos import openjev_opt as O

DATA = {"dev": E.DATASET, "heldout-v1": E.HELDOUT, "v2": Path("evals/data/systemone-heldout-v2.yaml"),
        **{k: Path(f"evals/data/openjev-v3-{k}.yaml") for k in ("cal", "opt", "final")}}
MODEL_SYSTEMS = {"base": ("baseline", False), "canon": ("canonical", False), "alias": ("alias", False), "ens": ("ensemble", False),
                 "base+pf": ("baseline", True), "canon+pf": ("canonical", True), "ens+pf": ("ensemble", True)}


def main(key, systems):
    cfg = C.load()
    out_dir = Path("audit/openjev-v3") / key
    out_dir.mkdir(parents=True, exist_ok=True)
    client = None
    try:
        for name in systems:
            out = out_dir / f"{name}.json"
            if out.exists():
                print("SKIP existing", out, flush=True)
                continue
            t0 = time.time()
            if name in MODEL_SYSTEMS:
                client = client or O.ScoreClient(cfg, cache_path="state/openjev-opt/cache.jsonl")
                mode, pf = MODEL_SYSTEMS[name]
                be = O.OpenJevBackend(client, mode, use_prefilter=pf, name=f"openjev:{name}")
                hits0, calls0 = client.hits, client.calls
                res = E.run_eval(cfg, be.name, dataset=DATA[key], backend=be)
                res["scorer"] = {"model_calls": client.calls - calls0, "cache_hits": client.hits - hits0, "runtime": dict(client.runtime.info)}
            elif name == "det":
                res = E.run_eval(cfg, "det", dataset=DATA[key], backend=O.OpenJevBackend(None, "deterministic", name="deterministic-prefilter"))
            elif name == "laya":
                try:
                    res = E.run_eval(cfg, "laya-mlx", dataset=DATA[key])
                finally:
                    A.close_all()
            elif name == "null":
                res = E.run_eval(cfg, "null", dataset=DATA[key])
            else:
                res = E.run_eval(cfg, f"baseline:{name}", dataset=DATA[key])
            res["wall_s"] = round(time.time() - t0, 1)
            out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
            print("DONE", key, name, res["wall_s"], "s", flush=True)
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(","))
