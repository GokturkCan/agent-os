#!/usr/bin/env python3
"""lookski/openjev masked-logit decision worker (Qwen3-0.6B): ONE backend behind agentos/systemone_adapter.py.

Runs inside the isolated runtime venv (state/runtime/openjev-masked). Same protocol and deterministic
option rendering (laya_worker.criteria_for) as the other workers; offline from `--model`, a local
snapshot directory of Qwen/Qwen3-0.6B at a pinned revision.

Method (upstream openjev.core.LocalJev, unchanged): ONE forward pass over a chat prompt that lists the
options as LETTERS A.. with ONLY their description text (option ids are not shown to the model), then a
softmax over the logits of the letter tokens at the first answer position. The letter is mapped back to the
option id in code. Consequences recorded in the audit: positional (letter) bias is possible; at most 26
options; the option id is invisible, so the description text must carry the information (for the `bare`
variant the id itself is the text). Probabilities are RAW masked-logit softmax values - never calibrated.
Single-option and invalid questions never reach the model.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laya_worker import criteria_for  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local Qwen3-0.6B snapshot directory")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--dtype", default="bfloat16")
    args = ap.parse_args()

    os.environ["HF_HUB_OFFLINE"] = "1"
    out = sys.stdout
    sys.stdout = sys.stderr

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    from importlib.metadata import version
    from openjev.core import LocalJev
    from openjev.types import Choice

    engine = LocalJev(model_id=args.model, device=args.device, dtype=args.dtype)

    def decide(state, prompt, criteria):
        t0 = time.perf_counter()
        ans = engine.answer_one(Choice(instructions=prompt, criteria=criteria), state)
        return ans, (time.perf_counter() - t0) * 1000.0

    decide("warm-up", "Pick one.", {"a": "first", "b": "second"})
    send({"ready": True, "runtime": {"openjev": "0.1.0+49eb138", "torch": version("torch"),
                                     "transformers": version("transformers"), "python": sys.version.split()[0],
                                     "device": args.device, "dtype": args.dtype}})

    for line in sys.stdin:
        qid = None
        try:
            req = json.loads(line)
            qid = req["question"]["id"]
            criteria, abstain = criteria_for(req)
            if isinstance(criteria, list):
                criteria = {c: c for c in criteria}
            criteria = {k: (v if v is not None else k) for k, v in criteria.items()}
            if len(criteria) < 2:
                (only,) = criteria
                send({"v": 1, "id": qid, "choice": only, "confidence": 1.0, "reason_code": "backend-choice"})
                continue
            state = req["state"]
            ans, _ms = decide(state, req["question"].get("prompt") or "Choose one.", criteria)
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
