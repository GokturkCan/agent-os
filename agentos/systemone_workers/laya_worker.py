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

R3.2C (additive; a payload without these fields behaves exactly as before): when the payload has
`option_info`, each criterion is described by deterministic text rendered from those structured
fields (never model-generated); when it has `allow_abstain`, an extra "none fits" label is offered
and choosing it is reported as `abstain`, which the adapter treats as an escalation.
"""
import argparse
import json
import sys


ABSTAIN_LABEL = "none_fits"
ABSTAIN_TEXT = ("no option fits: a required capability cannot be met, the risk is too high, or the "
                "information is insufficient; hand off to a human")


def describe(option: str, info: dict) -> str:
    """Deterministic one-line description of an option from its structured metadata."""
    parts = []
    if info.get("roles"):
        parts.append("roles: " + ", ".join(info["roles"]))
    if info.get("interactive") is False:
        parts.append("background only, not interactive")
    for key in ("access", "cost", "locality", "latency"):
        if info.get(key):
            parts.append(f"{key}: {info[key]}")
    if "missing" in info:
        parts.append("missing required capabilities: " + (", ".join(info["missing"]) or "none"))
    return "; ".join(parts) or option


def criteria_for(req: dict):
    """(criteria, abstain_label). A list of ids when no metadata/abstain is requested (legacy path)."""
    options, info = list(req["options"]), req.get("option_info") or {}
    abstain = None
    if info or req.get("allow_abstain"):
        criteria = {o: describe(o, info.get(o) or {}) for o in options}
    else:
        criteria = options
    if req.get("allow_abstain"):
        abstain = ABSTAIN_LABEL
        while abstain in options:
            abstain += "_"
        criteria[abstain] = ABSTAIN_TEXT
    return criteria, abstain


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
            criteria, abstain = criteria_for(req)
            result = agent.predict(req["state"], {qid: {"type": "choice",
                                                        "instructions": req["question"].get("prompt") or "Choose one.",
                                                        "criteria": criteria}})
            ans = result["answers"][qid]
            if abstain is not None and ans["choice"] == abstain:
                send({"v": 1, "id": qid, "abstain": True, "confidence": ans.get("answer_confidence")})
            else:
                send({"v": 1, "id": qid, "choice": ans["choice"], "confidence": ans.get("answer_confidence"),
                      "reason_code": "backend-choice"})
        except Exception as exc:                 # reported as a typed error; the adapter escalates
            send({"v": 1, "id": qid, "error": type(exc).__name__})
    return 0


if __name__ == "__main__":
    sys.exit(main())
