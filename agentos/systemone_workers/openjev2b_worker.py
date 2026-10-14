#!/usr/bin/env python3
"""Open-Jev-2B (ZefanCai) decision worker: ONE backend behind agentos/systemone_adapter.py.

Runs inside the isolated runtime venv (state/runtime/openjev2b). Same line protocol and the same
deterministic option rendering (laya_worker.criteria_for) as the other workers. Offline: the adapter
package is a local directory, the pinned base model (Qwen/Qwen3.5-2B @ 15852e8c) resolves from `--hf-home`.

Method (upstream, unchanged): each candidate `name: description` is scored INDEPENDENTLY by the LoRA'd
backbone + scalar head (no candidate order, no letters), then softmax with the checkpoint's saved
temperature. Backbone dtype is the released bfloat16 on MPS (no quantization, no fp32 upcast).
The upstream loader reads head.pt with torch.load(weights_only=True); this worker also forces it.
The reply carries the max-probability as a RAW confidence; no calibration claim is made here.
"""
import argparse
import functools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laya_worker import criteria_for  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local package/checkpoint directory")
    ap.add_argument("--hf-home", required=True)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()

    os.environ["HF_HOME"] = args.hf_home
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.pop("JEV_TORCH_DTYPE", None)      # keep the released bfloat16
    out = sys.stdout
    sys.stdout = sys.stderr

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    from importlib.metadata import version
    import torch
    torch.load = functools.partial(torch.load, weights_only=True)
    from jev.serving import load_predictor

    predictor = load_predictor(checkpoint=args.model, device=args.device, batch_size=args.batch_size)

    def decide(state, qid, prompt, criteria):
        res = predictor.predict({"state": state, "questions": {qid: {"type": "choice", "instructions": prompt,
                                                                      "criteria": criteria}}})
        return res["answers"][qid]

    decide("warm-up", "w", "Pick one.", {"a": None, "b": None})
    prov = {k: predictor.provenance.get(k) for k in ("base_revision", "backbone_parameter_dtypes", "max_length")}
    send({"ready": True, "runtime": {"open_jev_code": "bd411882", "torch": version("torch"),
                                     "transformers": version("transformers"), "peft": version("peft"),
                                     "python": sys.version.split()[0], "device": args.device, **prov}})

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
        except Exception as exc:
            send({"v": 1, "id": qid, "error": type(exc).__name__})
    return 0


if __name__ == "__main__":
    sys.exit(main())
