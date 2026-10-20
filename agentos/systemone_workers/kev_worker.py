#!/usr/bin/env python3
"""Kev-0.8B (MLX) decision worker: ONE backend implementation behind agentos/systemone_adapter.py.

Runs inside the isolated runtime venv (state/runtime/kev-mlx), never inside the agentos environment.
Same line protocol and the same deterministic option-description / abstain rendering as
laya_worker.py / decider_worker.py. Offline: the checkpoint is a local directory and the pinned base
model resolves from `--hf-home` with HF_HUB_OFFLINE=1.

Safe loading: Kev's `head.pt` is a torch pickle. Its opcodes were statically inspected (only
collections.OrderedDict, torch._utils._rebuild_tensor_v2, torch.FloatStorage) and, here, every
`torch.load` is forced to `weights_only=True` so nothing else can ever be unpickled.

The reply carries the chosen label and Kev's max-probability `confidence` as a RAW number (the
checkpoint folds its fitted temperature into the head; this layer applies no calibration of its own).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laya_worker import criteria_for  # noqa: E402  (pure functions; no laya import at module load)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local Kev checkpoint directory")
    ap.add_argument("--hf-home", required=True, help="HF cache holding the pinned base model")
    args = ap.parse_args()

    os.environ["HF_HOME"] = args.hf_home
    os.environ["HF_HUB_OFFLINE"] = "1"
    out = sys.stdout
    sys.stdout = sys.stderr                      # keep the protocol channel clean

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    from dataclasses import replace
    from importlib.metadata import version
    import functools
    import torch
    import mlx.core as mx

    torch.load = functools.partial(torch.load, weights_only=True)      # never unpickle arbitrary objects
    from kev.api import SystemOneRequest, to_answers, to_record
    from kev.checkpoint import Checkpoint, LoadOptions
    from kev.device import default_device
    from kev.model import admit

    ck = Checkpoint(args.model)
    tok, model = ck.load(default_device(), replace(LoadOptions.from_env({}), backend="mlx", dtype=torch.bfloat16))

    def decide(state, qid, prompt, criteria):
        req = SystemOneRequest(state=state, questions={qid: {"type": "choice", "instructions": prompt, "criteria": criteria}})
        rec, meta = to_record(req)
        probs = model.probs(admit(model, tok, rec, truncate=False))
        return to_answers([q.tolist() for q in probs], meta)[qid]

    decide("warm-up", "w", "Pick one.", {"a": None, "b": None})
    send({"ready": True, "runtime": {"kev": "0.1.0+6b719c3", "mlx": version("mlx"), "mlx_lm": version("mlx-lm"),
                                     "python": sys.version.split()[0], "device": str(mx.default_device())}})

    for line in sys.stdin:
        qid = None
        try:
            req = json.loads(line)
            qid = req["question"]["id"]
            criteria, abstain = criteria_for(req)
            if isinstance(criteria, list):
                criteria = {c: None for c in criteria}
            if len(criteria) < 2:                # a lone option is decided without the model
                (only,) = criteria
                send({"v": 1, "id": qid, "choice": only, "confidence": 1.0, "reason_code": "backend-choice"})
                continue
            ans = decide(req["state"], qid, req["question"].get("prompt") or "Choose one.", criteria)
            if abstain is not None and ans["choice"] == abstain:
                send({"v": 1, "id": qid, "abstain": True, "confidence": ans["confidence"]})
            else:
                send({"v": 1, "id": qid, "choice": ans["choice"], "confidence": ans["confidence"],
                      "reason_code": "backend-choice"})
        except Exception as exc:                 # reported as a typed error; the adapter escalates
            send({"v": 1, "id": qid, "error": type(exc).__name__})
    return 0


if __name__ == "__main__":
    sys.exit(main())
