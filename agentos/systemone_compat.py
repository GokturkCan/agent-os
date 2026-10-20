"""Opt-in TypeSafe/Jev-shaped compatibility mapping for SystemOne (R3.2G). Function + CLI only: no daemon, no dependency.

  agentos systemone-compat --eligible claude_code,codex [--backend null] < request.json

Maps a `/v1/systemone`-style body `{"state": ..., "questions": {id: {"type": "choice", "instructions": ..., "criteria":
{name: description|null}}}}` onto the Agent OS contract and back. The caller's body can NEVER widen the choice set: every
criteria key must be inside the explicitly supplied, policy-produced `eligible` set, otherwise the body is refused. Only
`choice` questions are supported (`noul`/`score` are refused, not approximated). Free-text option descriptions are not part
of the SystemOne contract (option metadata is an allowlist of config facts); they are passed as one bounded state note,
which the adapter redacts and truncates like any other state value.
Responses are typed: an answer carries `confidence_kind: "raw"`; an escalation carries the closed-vocabulary reason.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping, Sequence

from . import systemone as S

MAX_NOTE = 200


class CompatError(ValueError):
    pass


def to_requests(body: Mapping, eligible: Sequence[str], *, task_type: str = "compat", risk: str = "low",
                allow_abstain: bool = False) -> list[S.SystemOneRequest]:
    if not isinstance(body, Mapping) or "questions" not in body:
        raise CompatError("body needs questions")
    if not eligible:
        raise CompatError("an explicit policy-eligible option set is required")
    allowed = list(dict.fromkeys(eligible))
    state = body.get("state")
    base_state = dict(state) if isinstance(state, Mapping) else {"summary": str(state or "")[:MAX_NOTE]}
    qs = body["questions"]
    if not isinstance(qs, Mapping) or not qs:
        raise CompatError("questions must be a non-empty object")
    out = []
    for qid, q in qs.items():
        if not isinstance(qid, str) or not qid or qid.startswith("_escalation_"):
            raise CompatError("question id must be a non-empty string outside the reserved escalation namespace")
        if not isinstance(q, Mapping) or q.get("type") != "choice":
            raise CompatError(f"question {qid!r}: only type=choice is supported")
        crit = q.get("criteria")
        if not isinstance(crit, Mapping) or not crit:
            raise CompatError(f"question {qid!r}: criteria must be a non-empty object")
        extra = [k for k in crit if k not in allowed]
        if extra:
            raise CompatError(f"question {qid!r}: options outside the policy-eligible set: {sorted(map(str, extra))}")
        notes = "; ".join(f"{k}: {v}" for k, v in crit.items() if isinstance(v, str) and v.strip())
        st = dict(base_state)
        if notes:
            st["option_notes"] = notes[:MAX_NOTE]
        opts = tuple(k for k in allowed if k in crit)               # policy order, restricted to the asked options
        out.append(S.SystemOneRequest(task_type=task_type, risk=risk, eligible_options=opts, state=st,
                                      questions=(S.Question(str(qid), "choose", str(q.get("instructions") or "")[:MAX_NOTE]),),
                                      allow_abstain=allow_abstain))
    return out


def to_body(responses: list[S.SystemOneResponse], backend_name: str, latencies_ms: list[float] | None = None) -> dict:
    answers = {}
    for resp in responses:
        if resp.escalate:
            answers[f"_escalation_{len(answers)}"] = {"type": "escalate", "reason": resp.reason_code}
            continue
        for a in resp.answers:
            answers[a.question_id] = {"type": "choice", "choice": a.choice, "confidence": a.confidence.value,
                                      "confidence_kind": a.confidence.kind}
    body = {"model": backend_name, "answers": answers}
    if latencies_ms is not None:           # R3.5 observability: closed-vocabulary, no model text, no inputs
        body["trace"] = [{"question": i, "escalated": r.escalate, "reason": r.reason_code,
                          "fallback": "deterministic-policy" if r.escalate else None, "latency_ms": round(ms, 3)}
                         for i, (r, ms) in enumerate(zip(responses, latencies_ms))]
    return body


def decide(body: Mapping, eligible: Sequence[str], backend=None, **kw) -> dict:
    backend = backend or S.NullBackend()
    reqs = to_requests(body, eligible, **kw)
    responses, latencies = [], []
    for r in reqs:
        t0 = time.perf_counter()
        responses.append(S.system_one(r, backend))
        latencies.append((time.perf_counter() - t0) * 1000)
    return to_body(responses, getattr(backend, "name", "backend"), latencies)


def add_parser(sub) -> None:
    sp = sub.add_parser("systemone-compat", help="opt-in TypeSafe-shaped request -> SystemOne (stdin JSON, stdout JSON)")
    sp.add_argument("--eligible", required=True, help="comma-separated policy-eligible option ids (the only legal choices)")
    sp.add_argument("--backend", default="null", help="SystemOne backend (default null: always escalates)")


def run(cfg, a) -> int:
    try:
        body = json.loads(sys.stdin.read())
        backend = S.resolve_backend(a.backend, cfg)
        print(json.dumps(decide(body, [e for e in a.eligible.split(",") if e], backend), indent=2))
        return 0
    except (CompatError, ValueError) as exc:
        print(json.dumps({"error": str(exc)[:300]}))
        return 2
