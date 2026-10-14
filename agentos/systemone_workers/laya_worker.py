#!/usr/bin/env python3
"""Laya-MLX decision worker: ONE backend implementation behind agentos/systemone_adapter.py.

Runs inside the isolated runtime venv (state/runtime/laya-mlx), never inside the agentos
environment, and imports only the standard library plus laya_mlx. Protocol: after the model is
loaded and warmed up it prints `{"ready": true, "runtime": {...}}`, then answers each stdin line
(one JSON request) with exactly one stdout line. stdout carries protocol lines only; anything a
library prints is diverted to stderr. Offline: weights are loaded from a local directory.

Mapping: a `choose` question -> a Laya `choice` question whose criteria are the option ids;
the reply carries the chosen label and Laya's `answer_confidence` (max probability) as a RAW
number. Calibration is neither assumed nor applied here.
"""
import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local checkpoint directory")
    args = ap.parse_args()

    out = sys.stdout
    sys.stdout = sys.stderr                      # keep the protocol channel clean

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    import mlx.core as mx
    import laya_mlx as laya
    from importlib.metadata import version

    agent = laya.load(args.model, dtype="float16")
    warm_q = {"warmup": {"type": "choice", "instructions": "Pick one.", "criteria": ["a", "b"]}}
    agent.predict({"warmup": True}, warm_q)       # first call compiles kernels (~1.5 s); pay it at startup
    send({"ready": True, "runtime": {"laya_mlx": version("laya-mlx"), "mlx": version("mlx"),
                                     "python": sys.version.split()[0], "device": str(mx.default_device())}})

    for line in sys.stdin:
        qid = None
        try:
            req = json.loads(line)
            qid = req["question"]["id"]
            options = list(req["options"])
            result = agent.predict(req["state"], {qid: {"type": "choice",
                                                        "instructions": req["question"].get("prompt") or "Choose one.",
                                                        "criteria": options}})
            ans = result["answers"][qid]
            send({"v": 1, "id": qid, "choice": ans["choice"], "confidence": ans.get("answer_confidence"),
                  "reason_code": "backend-choice"})
        except Exception as exc:                 # reported as a typed error; the adapter escalates
            send({"v": 1, "id": qid, "error": type(exc).__name__})
    return 0


if __name__ == "__main__":
    sys.exit(main())
