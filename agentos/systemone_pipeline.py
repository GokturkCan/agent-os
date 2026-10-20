"""Lightweight SystemOne decision pipeline (R3.2G): prepare -> model -> validate -> verify, around ONE existing backend.

  C0 policy (router) -> eligible options -> PipelineBackend.decide()
      prepare   neutral per-request aliases for option ids (optional), ids inside state strings rewritten consistently
      model     strategy: `choice` (one question) | `per-option` (each option vs a fixed "none fits" anchor) |
                `consistency` (the choice question in several orders; disagreement escalates)
      validate  typed reply checks, alias round-trip, eligibility; any sub-call failure escalates (fail-closed)
  -> system_one() re-validates as for every backend.

The wrapped backend (e.g. the `laya-mlx` adapter) and its worker are unchanged: `strategy=choice, neutral=False` is the
vanilla path. Nothing here can add an option: aliases are a bijection on the request's own eligible ids, and an answer that
does not map back to one of them escalates `ineligible-choice`. Confidence stays `kind="raw"`.
Selected only explicitly (evaluation / bench specs `pipeline:<backend>:<neutral|raw>:<strategy>`); never a default.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import replace

from . import systemone as S
from . import systemone_adapter as A

STRATEGIES = ("choice", "per-option", "consistency")
ALIAS_PREFIX = "cand_"


# ------------------------------------------------------------ prepare
def aliases_for(request: S.SystemOneRequest) -> dict[str, str]:
    """Deterministic per-request neutral aliases. Derived from a hash of the request content and the option id (never from
    its list position), so the same request always maps the same way and different requests map differently."""
    basis = json.dumps({"t": request.task_type, "s": request.state, "c": list(request.required_capabilities),
                        "o": sorted(request.eligible_options)}, sort_keys=True, default=str)
    out, used = {}, set()
    for opt in sorted(request.eligible_options):
        salt = 0
        while True:
            alias = ALIAS_PREFIX + hashlib.sha256(f"{basis}|{opt}|{salt}".encode()).hexdigest()[:4]
            if alias not in used and alias not in request.eligible_options:
                break
            salt += 1
        out[opt] = alias
        used.add(alias)
    return out


def _rewrite(value, pattern: re.Pattern | None, mapping: dict[str, str]):
    if pattern is None:
        return value
    if isinstance(value, str):
        return pattern.sub(lambda m: mapping[m.group(0)], value)
    if isinstance(value, dict):
        return {k: _rewrite(v, pattern, mapping) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_rewrite(v, pattern, mapping) for v in value)
    return value


def neutralize(request: S.SystemOneRequest) -> tuple[S.SystemOneRequest, dict[str, str]]:
    """(aliased request, alias -> original id). Option metadata is carried over unchanged; only ids are renamed."""
    fwd = aliases_for(request)
    ids = sorted(fwd, key=len, reverse=True)
    pattern = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, ids)) + r")(?![A-Za-z0-9_])") if ids else None
    questions = tuple(replace(q, options=tuple(fwd.get(o, o) for o in q.options)) for q in request.questions)
    aliased = replace(
        request, questions=questions, eligible_options=tuple(fwd[o] for o in request.eligible_options),
        state=_rewrite(dict(request.state), pattern, fwd),
        option_info={fwd[k]: v for k, v in (request.option_info or {}).items() if k in fwd})
    return aliased, {v: k for k, v in fwd.items()}


# ------------------------------------------------------------ backend
class PipelineBackend:
    """A SystemOneBackend composed of explicit, separately switchable steps around one inner backend."""

    def __init__(self, inner, *, neutral: bool = False, strategy: str = "choice", name: str | None = None):
        if strategy not in STRATEGIES:
            raise ValueError(f"strategy must be one of {STRATEGIES}")
        self.inner, self.neutral, self.strategy = inner, bool(neutral), strategy
        self.name = name or f"pipeline:{getattr(inner, 'name', 'inner')}:{'neutral' if neutral else 'raw'}:{strategy}"
        self.traces: list[dict] = []
        self.keep_traces = 5000

    @property
    def runtime(self):
        return getattr(self.inner, "runtime", None)

    def close(self) -> None:
        close = getattr(self.inner, "close", None)
        if close:
            close()

    # -- helpers
    def _escalate(self, reason: str, trace: dict) -> S.SystemOneResponse:
        trace["result"] = f"escalate:{reason}"
        return S.SystemOneResponse((), True, reason, self.name)

    def _inner(self, request: S.SystemOneRequest, trace: dict) -> S.SystemOneResponse:
        t = time.perf_counter()
        trace["calls"] += 1
        try:
            resp = S.system_one(request, self.inner)
        finally:
            trace["model_ms"] += (time.perf_counter() - t) * 1000
        return resp

    def _score_option(self, request: S.SystemOneRequest, q: S.Question, opt: str, trace: dict) -> float:
        """P(opt) in a 2-way Laya question {opt, "none fits"}; raises AdapterReject on any failure."""
        sub = replace(request, eligible_options=(opt,), questions=(replace(q, options=(opt,)),), allow_abstain=True)
        payload = A.build_payload(sub, sub.questions[0])
        t = time.perf_counter()
        trace["calls"] += 1
        try:
            reply = self.inner.runtime.ask(payload, getattr(self.inner, "timeout", 2.0))
        finally:
            trace["model_ms"] += (time.perf_counter() - t) * 1000
        if not isinstance(reply, dict) or reply.get("v") != A.PROTOCOL_VERSION or reply.get("id") != payload["question"]["id"]:
            raise A.AdapterReject("malformed-output", "per-option reply")
        if "error" in reply:
            raise A.AdapterReject("backend-error", "per-option")
        if reply.get("abstain") is True and reply.get("choice") is not None:
            raise A.AdapterReject("malformed-output", "abstain combined with choice")
        conf = reply.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not math.isfinite(conf) or not 0 <= conf <= 1:
            raise A.AdapterReject("malformed-output", "per-option confidence")
        if reply.get("abstain") is True and reply.get("choice") is None:
            return 1.0 - float(conf)
        if reply.get("choice") == opt and "error" not in reply:
            return float(conf)
        if "error" in reply:
            raise A.AdapterReject("backend-error", "per-option")
        raise A.AdapterReject("ineligible-choice", "per-option")

    # -- strategies (each returns (choice, raw confidence) or raises AdapterReject / returns an escalation reason)
    def _choice(self, request, q, trace):
        resp = self._inner(replace(request, questions=(q,)), trace)
        if resp.escalate:
            return None, None, resp.reason_code
        a = resp.answer(q.id)
        return (a.choice, a.confidence.value, None) if a is not None else (None, None, "unanswered-question")

    def _per_option(self, request, q, trace):
        opts = [o for o in (q.options or request.eligible_options) if o in request.eligible_options]
        if len(opts) < 2:
            return self._choice(request, q, trace)
        scores = {o: self._score_option(request, q, o, trace) for o in opts}
        trace["scores"] = {o: round(s, 4) for o, s in scores.items()}
        best = max(opts, key=lambda o: (scores[o], -opts.index(o)))
        if request.allow_abstain and scores[best] < 0.5:
            return None, None, "backend-abstained"
        if sum(1 for o in opts if scores[o] == scores[best]) > 1:
            return None, None, "low-confidence"              # an exact tie is not a decision
        return best, scores[best], None

    def _consistency(self, request, q, trace):
        opts = [o for o in (q.options or request.eligible_options) if o in request.eligible_options]
        if len(opts) < 2:
            return self._choice(request, q, trace)
        orders = [tuple(opts), tuple(reversed(opts))]
        if len(opts) >= 3:
            orders.append(tuple(opts[1:] + opts[:1]))
        picks, confs = [], []
        for order in orders:
            sub = replace(request, eligible_options=order, questions=(replace(q, options=order),))
            choice, conf, reason = self._choice(sub, sub.questions[0], trace)
            if reason:
                return None, None, reason
            picks.append(choice)
            confs.append(conf)
        trace["picks"] = picks
        if len(set(picks)) != 1:
            return None, None, "low-confidence"
        known = [c for c in confs if c is not None]
        return picks[0], (min(known) if known else None), None

    # -- contract
    def decide(self, request: S.SystemOneRequest) -> S.SystemOneResponse:
        trace = {"strategy": self.strategy, "neutral": self.neutral, "calls": 0, "model_ms": 0.0}
        t0 = time.perf_counter()
        try:
            work, back = (neutralize(request) if self.neutral else (request, {o: o for o in request.eligible_options}))
            trace["prep_ms"] = (time.perf_counter() - t0) * 1000
            run = {"choice": self._choice, "per-option": self._per_option, "consistency": self._consistency}[self.strategy]
            answers = []
            for q in work.questions:
                if q.kind != "choose":
                    return self._escalate("unsupported-question", trace)
                choice, conf, reason = run(work, q, trace)
                if reason:
                    return self._escalate(reason, trace)
                original = back.get(choice) if isinstance(choice, str) else None
                if original is None or original not in request.eligible_options:
                    return self._escalate("ineligible-choice", trace)
                orig_q = next(x for x in request.questions if x.id == q.id)
                if orig_q.options and original not in orig_q.options:
                    return self._escalate("ineligible-choice", trace)
                confidence = S.Confidence(conf, "raw") if conf is not None else S.Confidence()
                answers.append(S.Answer(q.id, original, confidence, "backend-choice"))
            trace["result"] = "answer"
            return S.SystemOneResponse(tuple(answers), False, "backend-choice", self.name)
        except A.AdapterReject as exc:
            return self._escalate(exc.reason, trace)
        except Exception:                                         # never raise into the router
            return self._escalate("backend-error", trace)
        finally:
            trace["total_ms"] = (time.perf_counter() - t0) * 1000
            trace["overhead_ms"] = trace["total_ms"] - trace["model_ms"]
            if len(self.traces) < self.keep_traces:
                self.traces.append(trace)

    def summary(self) -> dict:
        """Aggregate provenance: model calls per decision and pipeline overhead (not model time)."""
        ts = self.traces
        if not ts:
            return {"decisions": 0}
        calls = sorted(t["calls"] for t in ts)
        over = sorted(t["overhead_ms"] for t in ts)
        pct = lambda xs, p: round(xs[min(len(xs) - 1, int(p * len(xs)))], 3)
        results: dict[str, int] = {}
        for t in ts:
            results[t.get("result", "?")] = results.get(t.get("result", "?"), 0) + 1
        return {"name": self.name, "strategy": self.strategy, "neutral": self.neutral, "decisions": len(ts),
                "model_calls_total": sum(calls), "model_calls_per_decision_mean": round(sum(calls) / len(ts), 3),
                "model_calls_per_decision_max": calls[-1], "overhead_ms_p50": pct(over, 0.5),
                "overhead_ms_p95": pct(over, 0.95), "results": results}


def from_spec(spec: str, cfg) -> PipelineBackend:
    """`pipeline:<backend>:<neutral|raw>:<strategy>` -> PipelineBackend around the configured backend."""
    parts = spec.split(":")
    if len(parts) != 4 or parts[0] != "pipeline" or parts[2] not in ("neutral", "raw") or parts[3] not in STRATEGIES:
        raise ValueError(f"pipeline spec must be pipeline:<backend>:<neutral|raw>:<{'|'.join(STRATEGIES)}>, got {spec!r}")
    inner = S.resolve_backend(parts[1], cfg)
    return PipelineBackend(inner, neutral=parts[2] == "neutral", strategy=parts[3], name=spec)
