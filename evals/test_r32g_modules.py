"""R3.2G opt-in modules: WakeGate, ContextGate, tool pruner, rule cache, compat mapping, calibration analysis, gates."""
import json
from pathlib import Path

import pytest

from agentos import contextgate as C
from agentos import rulecache as R
from agentos import systemone as S
from agentos import systemone_calibration as K
from agentos import systemone_compat as X
from agentos import toolpruner as P
from agentos import wakegate as W


class Fixed:
    """Backend that always answers `choice` (or escalates) and counts calls."""

    def __init__(self, choice=None, escalate=None):
        self.choice, self.escalate_reason, self.calls, self.name = choice, escalate, 0, "fixed"

    def decide(self, request):
        self.calls += 1
        if self.escalate_reason:
            return S.SystemOneResponse((), True, self.escalate_reason, self.name)
        q = request.questions[0]
        return S.SystemOneResponse((S.Answer(q.id, self.choice, S.Confidence(0.9, "raw")),), False, "backend-choice", self.name)


class Boom:
    name = "boom"

    def decide(self, request):
        raise RuntimeError("x")


# ------------------------------------------------------------ WakeGate
@pytest.mark.parametrize("event", [
    W.Event("message", "stop", from_user=True), W.Event("ci", "build FAILED"), W.Event("alert", "leaked api key"),
    W.Event("webhook", "migration", requires_approval=True), W.Event("webhook", "x", risk="high"),
    W.Event("calendar", "soon", deadline_minutes=5), W.Event("alert", "güvenlik ihlali")])
def test_must_wake_rules_never_consult_the_model(event):
    be = Fixed(W.DEFER)
    v = W.gate(event, W.WaitState("anything"), be)
    assert v.wake and v.reason.startswith("rule:") and be.calls == 0


@pytest.mark.parametrize("be", [Fixed(escalate="backend-timeout"), Boom(), Fixed(escalate="backend-abstained")])
def test_backend_failure_wakes(be):
    v = W.gate(W.Event("email", "newsletter"), W.WaitState("reply"), be)
    assert v.action == W.WAKE_LOCAL and v.reason.startswith("fallback:")


def test_no_change_defers_and_skip_limit_wakes():
    obs = {"price": 1}
    st = W.WaitState("price", W.observation_sha(obs))
    assert W.gate(W.Event("timer", observation=obs), st, Fixed(W.WAKE_LOCAL)).reason == "rule:no-change"
    st = W.WaitState("reply", skipped=10, max_skips=10)
    be = Fixed(W.DEFER)
    assert W.gate(W.Event("email", "digest"), st, be).reason == "skip-limit" and be.calls == 0
    st = W.WaitState("reply")
    assert not W.gate(W.Event("email", "digest"), st, Fixed(W.DEFER)).wake and st.skipped == 1


def test_rules_only_mode_wakes_undecided_events():
    v = W.gate(W.Event("email", "digest"), W.WaitState("reply"), None, use_model=False)
    assert v.wake and v.reason == "fallback:no-model"


# ------------------------------------------------------------ ContextGate
def _items(result_text):
    its = [C.Item("u", "user", "text", "Fix it. Never touch prod."), C.Item("c", "assistant", "tool_call", "$ make")]
    its.append(C.Item("r", "tool", "tool_result", result_text, "bash"))
    its += [C.Item(f"f{i}", "assistant", "text", "ok") for i in range(8)]
    return its


def test_protected_lines_survive_a_model_drop(tmp_path):
    text = "\n".join(["noise line"] * 300 + ["src/app/main.py:12: error E1001: boom", "done"])
    res = C.compact(_items(text), C.Store(tmp_path), backend=Fixed(C.DROP))
    d = next(x for x in res.decisions if x["id"] == "r")
    view = next(v for v in res.view if v["id"] == "r")["text"]
    assert d["action"] == C.TRUNCATE and "E1001" in view and "src/app/main.py:12" in view
    assert C.recover(view, C.Store(tmp_path)) == text


def test_user_text_and_structured_results_are_never_compacted(tmp_path):
    js = json.dumps({"k": list(range(500))})
    res = C.compact(_items(js), C.Store(tmp_path), backend=Fixed(C.DROP))
    assert all(d["action"] == C.KEEP for d in res.decisions)
    assert res.view[0]["text"] == "Fix it. Never touch prod."


def test_unprotected_drop_leaves_recoverable_marker_and_escalation_uses_default(tmp_path):
    text = "\n".join(["plain words here"] * 400)
    st = C.Store(tmp_path)
    res = C.compact(_items(text), st, backend=Fixed(C.DROP))
    view = next(v for v in res.view if v["id"] == "r")["text"]
    assert view.startswith("[contextgate: dropped") and C.recover(view, st) == text
    res = C.compact(_items(text), st, backend=Fixed(escalate="backend-timeout"))
    assert next(x for x in res.decisions if x["id"] == "r")["action"] == C.TRUNCATE


def test_store_refuses_secondbrain():
    with pytest.raises(ValueError):
        C.Store(C.SECONDBRAIN / "derived")


# ------------------------------------------------------------ tool pruner
def test_pruner_passthrough_small_and_structured(tmp_path):
    st = C.Store(tmp_path)
    assert P.prune("ok", st).view == "ok"
    big_json = json.dumps([{"i": i} for i in range(3000)])
    assert P.prune(big_json, st).stats["path"] == "passthrough"


def test_pruner_keeps_protected_and_edges_and_is_recoverable(tmp_path):
    st = C.Store(tmp_path)
    out = "\n".join(["start"] + [f"compiling unit {i} ok {i * 7}" for i in range(3000)]
                    + ["src/x.c:9: error E77: bad", "Status: finished OK"])
    r = P.prune(out, st, backend=Fixed(P.DROP_CHUNK))
    assert "src/x.c:9: error E77: bad" in r.view and "Status: finished OK" in r.view and "start" in r.view
    assert st.get(r.sha256) == out and r.stats["tokens_after"] < r.stats["tokens_before"]


# ------------------------------------------------------------ rule cache
def _req(opts=("claude_code", "codex")):
    return S.SystemOneRequest("coding", (S.Question("worker", "choose", "w"),), tuple(opts), {"task_class": "coding"})


def test_rule_cache_requires_human_approval_and_exact_scope(tmp_path):
    cache, h = R.RuleCache(tmp_path / "r.yaml"), "a" * 64
    rule = cache.propose(_req(), S.PolicyOrderBackend().decide(_req()), h, "evidence")
    cb = R.CachedBackend(S.NullBackend(), cache, h)
    assert S.system_one(_req(), cb).escalate                     # proposed only: no effect
    with pytest.raises(ValueError):
        cache.approve(rule["id"], "model")
    cache.approve(rule["id"], "human:owner")
    assert S.system_one(_req(), cb).answer("worker").choice == "claude_code"
    assert cache.lookup(_req(("codex",)), h) is None and cache.lookup(_req(), "b" * 64) is None
    with pytest.raises(ValueError):
        cache.propose(_req(), S.NullBackend().decide(_req()), h, "evidence")


# ------------------------------------------------------------ compat
def test_compat_cannot_widen_options_and_maps_back():
    body = {"state": "write tests", "questions": {"w": {"type": "choice", "instructions": "who?",
                                                        "criteria": {"codex": "tests", "claude_code": None}}}}
    with pytest.raises(X.CompatError):
        X.to_requests(body, ["codex"])
    with pytest.raises(X.CompatError):
        X.to_requests({"questions": {"q": {"type": "noul", "instructions": "x"}}}, ["codex"])
    out = X.decide(body, ["claude_code", "codex"], Fixed("codex"))
    assert out["answers"]["w"] == {"type": "choice", "choice": "codex", "confidence": 0.9, "confidence_kind": "raw"}
    assert X.decide(body, ["claude_code", "codex"])["answers"]["_escalation_0"]["reason"] == "no-backend"
    bad = X.decide(body, ["claude_code", "codex"], Fixed("gemini"))
    assert bad["answers"]["_escalation_0"]["reason"] == "ineligible-choice"


# ------------------------------------------------------------ calibration analysis
def test_calibration_metrics_and_maps():
    ps = [(0.9, 1)] * 9 + [(0.9, 0)] + [(0.6, 1)] * 3 + [(0.6, 0)] * 7
    rel = K.reliability(ps)
    assert rel["n"] == 20 and abs(rel["ece"] - 0.15) < 1e-6 and rel["auroc"] is not None
    iso = K.fit_isotonic(ps)
    assert iso["y"] == sorted(iso["y"])
    assert K.apply_map(iso, 0.9) == pytest.approx(0.9) and K.apply_map(iso, 0.6) == pytest.approx(0.3)
    pl = K.fit_platt(ps)
    assert K.apply_map(pl, 0.9) > K.apply_map(pl, 0.6)


def test_calibration_reads_only_raw_answered_records():
    res = {"records": [{"variant": "described", "escalated": False, "conf_kind": "raw", "conf_value": 0.7, "outcome": "correct"},
                       {"variant": "described", "escalated": True, "conf_kind": None, "conf_value": None, "outcome": "escalated"},
                       {"variant": "bare", "escalated": False, "conf_kind": "raw", "conf_value": 0.9, "outcome": "correct"}]}
    assert K.points(res, "described") == [(0.7, 1)]
