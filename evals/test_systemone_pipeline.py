"""R3.2G lightweight SystemOne pipeline: preparation, strategies, validation, fail-closed behaviour (no model needed)."""
import pytest

from agentos import systemone as S
from agentos import systemone_adapter as A
from agentos.systemone_pipeline import PipelineBackend, aliases_for, from_spec, neutralize


def req(opts=("claude_code", "codex"), info=None, state=None, abstain=False):
    return S.SystemOneRequest(task_type="coding", questions=(S.Question("worker", "choose", "Which worker?"),),
                              eligible_options=tuple(opts), state=state or {"summary": "write tests"},
                              option_info=info or {}, allow_abstain=abstain)


class FakeRuntime:
    """Answers protocol-v1 payloads: chooses the option whose metadata has role `want` (else the first)."""

    def __init__(self, want="tests", scores=None, raw=None):
        self.want, self.scores, self.raw, self.calls = want, scores or {}, raw, []

    def ask(self, payload, timeout):
        self.calls.append(payload)
        if self.raw is not None:
            return self.raw
        opts, info = payload["options"], payload.get("option_info", {})
        if payload.get("allow_abstain") and len(opts) == 1:          # per-option 2-way anchor question
            o = opts[0]
            p = self.scores.get(tuple(info.get(o, {}).get("roles", [])), 0.6)
            return {"v": 1, "id": payload["question"]["id"], "choice": o, "confidence": p} if p >= 0.5 else \
                {"v": 1, "id": payload["question"]["id"], "abstain": True, "confidence": 1 - p}
        pick = next((o for o in opts if self.want in info.get(o, {}).get("roles", [])), opts[0])
        return {"v": 1, "id": payload["question"]["id"], "choice": pick, "confidence": 0.7}

    def close(self):
        pass


def inner(rt):
    return A.AdapterBackend("fake", rt)


INFO = {"claude_code": {"roles": ["architecture"]}, "codex": {"roles": ["tests"]}}


def test_aliases_deterministic_bijective_and_not_positional():
    a = aliases_for(req(("claude_code", "codex")))
    b = aliases_for(req(("codex", "claude_code")))
    assert a == b and len(set(a.values())) == 2
    assert all(v.startswith("cand_") and v not in ("claude_code", "codex") for v in a.values())
    assert aliases_for(req(state={"summary": "other"})) != a          # per request, not a fixed table


def test_neutralize_rewrites_whole_word_ids_in_state_only():
    r = req(("w_one", "w_two"), state={"summary": "Review the change written by w_two (not w_two_x).",
                                         "primary_worker": "w_two", "nested": ["w_one"]})
    al, back = neutralize(r)
    fwd = {v: k for k, v in back.items()}
    assert al.state["primary_worker"] == fwd["w_two"]
    assert f"written by {fwd['w_two']} (not w_two_x)" in al.state["summary"]
    assert al.state["nested"] == [fwd["w_one"]]
    assert set(al.eligible_options) == set(fwd.values())


def test_vanilla_path_equals_inner_backend():
    rt = FakeRuntime()
    r = req(info=INFO)
    assert S.system_one(r, PipelineBackend(inner(rt))).answer("worker").choice == \
        S.system_one(r, inner(FakeRuntime())).answer("worker").choice == "codex"


def test_neutral_maps_back_and_hides_ids():
    rt = FakeRuntime()
    resp = S.system_one(req(info=INFO), PipelineBackend(inner(rt), neutral=True))
    assert not resp.escalate and resp.answer("worker").choice == "codex"
    assert all(o.startswith("cand_") for o in rt.calls[0]["options"])
    assert "claude_code" not in str(rt.calls[0]) and "codex" not in str(rt.calls[0])


def test_unmappable_answer_escalates():
    rt = FakeRuntime(raw={"v": 1, "id": "worker", "choice": "codex", "confidence": 0.9})   # real id, not an alias
    resp = S.system_one(req(info=INFO), PipelineBackend(inner(rt), neutral=True))
    assert resp.escalate and resp.reason_code == "ineligible-choice"


def test_per_option_argmax_abstain_and_call_count():
    rt = FakeRuntime(scores={("architecture",): 0.55, ("tests",): 0.8})
    b = PipelineBackend(inner(rt), strategy="per-option")
    resp = S.system_one(req(info=INFO), b)
    assert resp.answer("worker").choice == "codex" and resp.answer("worker").confidence.kind == "raw"
    assert len(rt.calls) == 2 and b.summary()["model_calls_per_decision_mean"] == 2
    low = FakeRuntime(scores={("architecture",): 0.2, ("tests",): 0.3})
    resp = S.system_one(req(info=INFO, abstain=True), PipelineBackend(inner(low), strategy="per-option"))
    assert resp.escalate and resp.reason_code == "backend-abstained"
    resp = S.system_one(req(info=INFO, abstain=False), PipelineBackend(inner(low), strategy="per-option"))
    assert resp.answer("worker").choice == "codex"                    # abstention only when the request allows it


def test_per_option_tie_and_malformed_escalate():
    tie = FakeRuntime(scores={("architecture",): 0.7, ("tests",): 0.7})
    assert S.system_one(req(info=INFO), PipelineBackend(inner(tie), strategy="per-option")).reason_code == "low-confidence"
    bad = FakeRuntime(raw={"v": 1, "id": "worker", "choice": "codex", "confidence": 7})
    assert S.system_one(req(info=INFO), PipelineBackend(inner(bad), strategy="per-option")).reason_code == "malformed-output"


class OrderRuntime(FakeRuntime):
    def ask(self, payload, timeout):
        self.calls.append(payload)
        return {"v": 1, "id": payload["question"]["id"], "choice": payload["options"][0], "confidence": 0.6}


def test_consistency_escalates_on_disagreement_and_accepts_agreement():
    b = PipelineBackend(inner(OrderRuntime()), strategy="consistency")
    resp = S.system_one(req(info=INFO), b)
    assert resp.escalate and resp.reason_code == "low-confidence" and b.traces[-1]["calls"] == 2
    rt = FakeRuntime()
    resp = S.system_one(req(("claude_code", "codex", "deepseek_harness"), info=INFO),
                        PipelineBackend(inner(rt), strategy="consistency"))
    assert resp.answer("worker").choice == "codex" and len(rt.calls) == 3


class Boom:
    name, timeout = "boom", 1.0

    def decide(self, request):
        raise RuntimeError("x")


@pytest.mark.parametrize("strategy", ["choice", "per-option", "consistency"])
def test_failures_never_raise(strategy):
    resp = S.system_one(req(info=INFO), PipelineBackend(Boom(), strategy=strategy, neutral=True))
    assert resp.escalate and resp.reason_code == "backend-error"


def test_single_option_passes_through():
    rt = FakeRuntime()
    resp = S.system_one(req(("codex",), info=INFO), PipelineBackend(inner(rt), strategy="per-option", neutral=True))
    assert resp.answer("worker").choice == "codex" and len(rt.calls) == 1


def test_spec_validation():
    with pytest.raises(ValueError):
        from_spec("pipeline:laya-mlx:maybe:choice", cfg=None)
    with pytest.raises(ValueError):
        PipelineBackend(Boom(), strategy="vote")
