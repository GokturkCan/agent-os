#!/usr/bin/env python3
"""Open-Jev-2B RESEARCH scorer (R3.2H): returns the full per-candidate probability vector. Not a SystemOne backend.

Runs inside the isolated runtime venv (state/runtime/openjev2b), offline, same checkpoint/loader/dtype as openjev2b_worker.py (which stays the
unchanged baseline). One JSON object per line:
  in : {"state": ..., "prompt": str, "criteria": [[key, description|null], ...]}      (candidate ORDER is the caller's)
  out: {"probs": [p_1..p_n], "ms": float}   in the same order; or {"error": ExcName}
The ready message reports load_s / warmup_s separately (cold-start attribution). `--idle-exit-seconds N` (0 = never) makes the worker exit when idle so
the adapter-style runtime restarts it lazily on the next call (frees ~6 GiB; the next call pays the full cold start).
"""
import argparse
import functools
import json
import os
import select
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--hf-home", required=True)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--idle-exit-seconds", type=float, default=0.0)
    args = ap.parse_args()
    os.environ["HF_HOME"] = args.hf_home
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.pop("JEV_TORCH_DTYPE", None)
    out = sys.stdout
    sys.stdout = sys.stderr

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    from importlib.metadata import version
    import torch
    torch.load = functools.partial(torch.load, weights_only=True)
    from jev.serving import load_predictor

    t0 = time.perf_counter()
    predictor = load_predictor(checkpoint=args.model, device=args.device, batch_size=args.batch_size)
    load_s = time.perf_counter() - t0

    def score(state, prompt, criteria):
        crit = {k: d for k, d in criteria}
        res = predictor.predict({"state": state, "questions": {"q": {"type": "choice", "instructions": prompt, "criteria": crit}}})
        probs = res["answers"]["q"]["probabilities"]
        return [probs[k] for k, _ in criteria]

    t1 = time.perf_counter()
    score("warm-up", "Pick one.", [["a", None], ["b", None]])
    warm_s = time.perf_counter() - t1
    send({"ready": True, "runtime": {"torch": version("torch"), "transformers": version("transformers"), "python": sys.version.split()[0],
                                     "device": args.device, "load_s": round(load_s, 3), "warmup_s": round(warm_s, 3),
                                     "temperature": getattr(predictor, "temperature", None)}})
    idle = args.idle_exit_seconds
    while True:
        if idle > 0 and not select.select([sys.stdin], [], [], idle)[0]:
            return 0
        line = sys.stdin.readline()
        if not line:
            return 0
        try:
            req = json.loads(line)
            t = time.perf_counter()
            probs = score(req["state"], req.get("prompt") or "Choose one.", req["criteria"])
            send({"probs": probs, "ms": round((time.perf_counter() - t) * 1000, 3)})
        except Exception as exc:
            send({"error": type(exc).__name__})


if __name__ == "__main__":
    sys.exit(main())
