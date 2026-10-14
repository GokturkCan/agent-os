#!/usr/bin/env python3
"""Strands Decider (MLX) decision worker: ONE backend implementation behind agentos/systemone_adapter.py.

Runs inside the isolated runtime venv (state/runtime/decider-mlx), never inside the agentos
environment. Same line protocol as laya_worker.py (one JSON request per stdin line, exactly one
stdout line per request; stdout carries protocol lines only). Fully offline: the LoRA checkpoint is a
local directory and the pinned base model is resolved from `--hf-home` with HF_HUB_OFFLINE=1.

The option description / abstain rendering is shared with laya_worker.py so the two backends see the
same deterministic prompt content. A `choose` question becomes a Decider `choice` question; the reply
carries the chosen label and the model's max-probability `confidence` as a RAW number (the checkpoint
ships its own temperature, but this layer neither assumes nor applies calibration).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laya_worker import criteria_for  # noqa: E402  (pure functions; no laya import at module load)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local Decider checkpoint directory")
    ap.add_argument("--hf-home", required=True, help="HF cache holding the pinned base model")
    args = ap.parse_args()

    os.environ["HF_HOME"] = args.hf_home
    os.environ["HF_HUB_OFFLINE"] = "1"
    out = sys.stdout
    sys.stdout = sys.stderr                      # keep the protocol channel clean

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    from importlib.metadata import version
    import mlx.core as mx
    from strands_decider.infer import load_engine

    engine = load_engine(args.model, device="mlx")
    engine.ask("warm-up", {"w": {"type": "choice", "instructions": "Pick one.", "criteria": {"a": None, "b": None}}})
    send({"ready": True, "runtime": {"strands_decider": version("strands-decider"), "mlx": version("mlx"),
                                     "python": sys.version.split()[0], "device": str(mx.default_device())}})

    for line in sys.stdin:
        qid = None
        try:
            req = json.loads(line)
            qid = req["question"]["id"]
            criteria, abstain = criteria_for(req)
            if isinstance(criteria, list):
                criteria = {c: None for c in criteria}
            if len(criteria) < 2:                # Decider's schema requires >= 2 options; a lone option
                (only,) = criteria               # is decided without the model (stated, not inferred)
                send({"v": 1, "id": qid, "choice": only, "confidence": 1.0, "reason_code": "backend-choice"})
                continue
            state = req["state"]
            resp = engine.ask(state if isinstance(state, (str, dict, list)) else str(state),
                              {qid: {"type": "choice",
                                     "instructions": req["question"].get("prompt") or "Choose one.",
                                     "criteria": criteria}})
            ans = resp.answers[qid]
            if abstain is not None and ans.choice == abstain:
                send({"v": 1, "id": qid, "abstain": True, "confidence": ans.confidence})
            else:
                send({"v": 1, "id": qid, "choice": ans.choice, "confidence": ans.confidence,
                      "reason_code": "backend-choice"})
        except Exception as exc:                 # reported as a typed error; the adapter escalates
            send({"v": 1, "id": qid, "error": type(exc).__name__})
    return 0


if __name__ == "__main__":
    sys.exit(main())
