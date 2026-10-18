"""Lazy lifecycle probe (R3.2H): idle exit then restart on a DIFFERENT request (the first bench run re-asked the same cached request by mistake;
that evidence is kept in bench.json). Writes audit/openjev-v3/bench-lazy.json, refuses to overwrite."""
import json
import time
from pathlib import Path

from agentos import config as C, systemone_eval as E, openjev_opt as O

cfg = C.load()
data = E.load_dataset(Path("evals/data/openjev-v3-opt.yaml"))
reqs = [E.build_request(cfg, c, tuple(c["request"]["eligible_options"]), "described") for c in data["cases"]
        if len(c["request"]["eligible_options"]) == 2 and not c["gold"].get("escalate") and c["lang"] == "en"][:3]
lz = O.ScoreClient(cfg, cache_path=None, idle_exit_seconds=6.0)
out = {"idle_exit_seconds": 6}
try:
    be = O.OpenJevBackend(lz, "baseline")
    t = time.perf_counter(); be.decide(reqs[0]); out["cold_first_decision_s"] = round(time.perf_counter() - t, 2)
    t = time.perf_counter(); be.decide(reqs[1]); out["warm_second_decision_s"] = round(time.perf_counter() - t, 3)
    time.sleep(10)
    out["process_exited_when_idle"] = lz.runtime.pid is None
    out["system_free_percent_while_idle"] = O.system_free_percent()
    t = time.perf_counter(); be.decide(reqs[2]); out["restart_first_decision_s"] = round(time.perf_counter() - t, 2)
    out["restart_worker_ready"] = dict(lz.runtime.info)
finally:
    lz.close()
p = Path("audit/openjev-v3/bench-lazy.json")
assert not p.exists()
p.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
