"""R3.2H Open-Jev study code and v3 partitions. Offline: a stub scorer stands in for the model (no inference, no process spawn)."""
import collections
import hashlib
import json
from pathlib import Path

import pytest

from agentos import config as C
from agentos import openjev_opt as O
from agentos import systemone as S
from agentos import systemone_eval as E

ROOT = Path(__file__).parents[1]
PART = {k: ROOT / "evals" / "data" / f"openjev-v3-{k}.yaml" for k in ("cal", "opt", "final")}


class StubClient:
    """Deterministic fake scorer: probability depends on the candidate text only (like the real independent-candidate scoring)."""

    def __init__(self, bias=None):
        self.bias, self.calls = bias or {}, []

    def score(self, state, prompt, criteria):
        self.calls.append([k for k, _ in criteria])
        raw = [self.bias.get(k, 1.0) + (int(hashlib.sha256(f"{k}{d}".encode()).hexdigest(), 16) % 7) / 100 for k, d in criteria]
        z = sum(raw)
        return [x / z for x in raw]


def req(options=("claude_code", "codex"), **kw):
    base = dict(task_type="coding", eligible_options=tuple(options), state={"task_class": "coding", "summary": "do the thing"},
                questions=(S.Question("worker", "choose", "Which worker?"),), risk="low")
    return S.SystemOneRequest(**{**base, **kw})


# ------------------------------------------------------------------ partitions
def test_v3_partitions_are_frozen_and_independent():
    fz = json.loads((ROOT / "audit/openjev-v3/freeze.json").read_text())["files"]
    for k, p in PART.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == fz[f"evals/data/openjev-v3-{k}.yaml"], k
    fams = {}
    for k, p in PART.items():
        d = E.load_dataset(p)
        fams[k] = {c["id"].rsplit("-", 2)[0] for c in d["cases"]}
        assert {c["lang"] for c in d["cases"]} == {"en", "tr"}
        assert {c["id"].rsplit("-", 1)[1] for c in d["cases"]} == {"real", "misleading"}
    assert not (fams["cal"] & fams["opt"]) and not (fams["cal"] & fams["final"]) and not (fams["opt"] & fams["final"])
    assert sum(len(v) for v in fams.values()) >= 100
    assert len(fams["final"]) > len(fams["cal"]) and len(fams["final"]) > len(fams["opt"])


def test_v3_covers_the_requested_decision_types():
    cats = collections.Counter()
    for p in PART.values():
        cats.update(c["category"] for c in E.load_dataset(p)["cases"])
    for needed in ("adversarial_order", "insufficient_info", "equally_acceptable", "conflicting_info", "risk_routing", "approval_boundary",
                   "review_independence", "dynamic_capability", "escalation", "label_bias", "description_bias", "worker_failure"):
        assert cats[needed] > 0, needed
    d = E.load_dataset(PART["final"])
    cp = [c for c in d["cases"] if not c["gold"].get("escalate") and "claude_code" not in c["gold"]["acceptable"]
          and "test_expert" not in c["gold"]["acceptable"]]
    assert cp, "counter-prior cases (gold excludes the label-prior first choice) must exist"


def test_final_partition_has_no_model_output_before_the_prerun_record():
    pre = json.loads((ROOT / "audit/openjev-v3/final-prerun.json").read_text())["files"]
    assert hashlib.sha256(PART["final"].read_bytes()).hexdigest() == pre["evals/data/openjev-v3-final.yaml"]


# ------------------------------------------------------------------ prefilter: only ever removes
def test_prefilter_removes_but_never_adds():
    r = req(("claude_code", "codex", "deepseek_harness"), state={"interactive": True, "primary_worker": "codex"},
            option_info={"deepseek_harness": {"interactive": False}, "codex": {}, "claude_code": {}})
    left, why = O.prefilter(r)
    assert why is None and left == ["claude_code"] and set(left) <= set(r.eligible_options)
    assert O.prefilter(req(risk="high", state={"human_approval": False})) == ([], "no-eligible-options")
    assert O.prefilter(req(risk="high", state={"human_approval": True}))[1] is None
    assert O.prefilter(req(option_info={"claude_code": {"missing": ["web.crawl"]}, "codex": {"missing": ["web.crawl"]}})) == ([], "no-eligible-options")
    # a lone option is never dropped by the primary/previous rule (nothing to hand over to)
    assert O.prefilter(req(("codex",), state={"primary_worker": "codex"}))[0] == ["codex"]
    assert O.prefilter(req(cost_profile="subscription_first", option_info={"deepseek_harness": {"access": "api"}, "codex": {"access": "harness"}},
                           eligible_options=("deepseek_harness", "codex")))[0] == ["codex"]


# ------------------------------------------------------------------ backend modes
def test_canonical_decision_is_independent_of_option_order():
    be = O.OpenJevBackend(StubClient(), "canonical")
    a = be.decide(req(("claude_code", "codex", "deepseek_harness")))
    b = be.decide(req(("deepseek_harness", "claude_code", "codex")))
    assert a.answer("worker").choice == b.answer("worker").choice
    assert be.client.calls[0] == sorted(be.client.calls[0]) == be.client.calls[1]


def test_baseline_keeps_caller_order_like_the_shipped_worker():
    c = StubClient()
    O.OpenJevBackend(c, "baseline").decide(req(("codex", "claude_code")))
    assert c.calls[0] == ["codex", "claude_code"]


def test_tie_break_is_lowest_id_when_canonical_and_first_when_baseline():
    class Flat(StubClient):
        def score(self, state, prompt, criteria):
            return [1.0 / len(criteria)] * len(criteria)
    assert O.OpenJevBackend(Flat(), "canonical").decide(req(("codex", "claude_code"))).answer("worker").choice == "claude_code"
    assert O.OpenJevBackend(Flat(), "baseline").decide(req(("codex", "claude_code"))).answer("worker").choice == "codex"


def test_alias_mode_maps_back_and_never_exposes_ids_to_the_scorer():
    c = StubClient()
    r = req(state={"summary": "ask claude_code about it"}, option_info={"claude_code": {"roles": ["architecture"]}, "codex": {"roles": ["tests"]}})
    resp = O.OpenJevBackend(c, "alias").decide(r)
    assert not resp.escalate and resp.answer("worker").choice in ("claude_code", "codex")
    assert all(k.startswith("cand_") for k in c.calls[0])


def test_ensemble_averages_the_two_views_and_stays_inside_the_eligible_set():
    be = O.OpenJevBackend(StubClient(), "ensemble")
    resp = be.decide(req())
    assert resp.answer("worker").choice in ("claude_code", "codex") and len(be.client.calls) == 2


def test_choice_is_always_inside_the_eligible_set_and_confidence_is_raw():
    for mode in ("baseline", "canonical", "alias", "ensemble"):
        for pf in (False, True):
            resp = O.OpenJevBackend(StubClient({"codex": 3.0}), mode, use_prefilter=pf).decide(req(("claude_code", "codex", "deepseek_harness")))
            assert resp.answer("worker").choice in ("claude_code", "codex", "deepseek_harness")
            assert resp.answer("worker").confidence.kind in ("raw", "none")


def test_abstain_candidate_and_tau_escalate_instead_of_choosing():
    resp = O.OpenJevBackend(StubClient({"none_fits": 50.0}), "canonical").decide(req(allow_abstain=True))
    assert resp.escalate and resp.reason_code == "backend-abstained"
    low = O.OpenJevBackend(StubClient(), "canonical", tau=0.99).decide(req())
    assert low.escalate and low.reason_code == "low-confidence"


def test_prefilter_singleton_and_empty_never_call_the_model():
    c = StubClient()
    be = O.OpenJevBackend(c, "alias", use_prefilter=True)
    one = be.decide(req(state={"previous_worker": "claude_code"}))
    assert one.answer("worker").choice == "codex" and c.calls == []
    assert be.decide(req(risk="high", state={"human_approval": False})).escalate and c.calls == []


def test_deterministic_system_needs_no_client():
    d = O.OpenJevBackend(None, "deterministic").decide(req(("codex", "claude_code")))
    assert d.answer("worker").choice == "claude_code" and d.answer("worker").confidence.kind == "none"


# ------------------------------------------------------------------ client safety
def test_offline_client_never_starts_a_model(cfg):
    c = O.ScoreClient(cfg, cache_path=None, offline=True)
    with pytest.raises(KeyError):
        c.score({"a": 1}, "p", [["x", None], ["y", None]])
    assert c.runtime.pid is None


def test_cache_key_depends_on_candidate_order_and_text():
    k = O.ScoreClient.key
    assert k({"s": 1}, "p", [["a", "d"], ["b", None]]) != k({"s": 1}, "p", [["b", None], ["a", "d"]])
    assert k({"s": 1}, "p", [["a", "d"]]) != k({"s": 1}, "p", [["a", "e"]])


def test_memory_guard_stops_a_thrashing_run(cfg, monkeypatch):
    c = O.ScoreClient(cfg, cache_path=None)
    c.model_ms = [9000.0] * 11
    closed = []
    monkeypatch.setattr(c.runtime, "ask", lambda payload, timeout: {"probs": [0.5, 0.5], "ms": 9000.0})
    monkeypatch.setattr(c.runtime, "close", lambda: closed.append(1))
    with pytest.raises(O.MemoryThrash):
        c.score({"s": 1}, "p", [["a", None], ["b", None]])
    assert closed


# ------------------------------------------------------------------ nothing is activated
def test_study_code_is_not_registered_or_activated(cfg):
    assert set(S.BACKENDS) == {"null", "policy-order"} and "openjev" not in " ".join(S.BACKENDS)
    assert "openjev_scorer" not in json.dumps(cfg.systemone)
    assert cfg.routing["systemone"]["backend"] == "null" and cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.systemone["activation"] == {"production_backends": [], "fastgate_models": []}
    assert C.validate(cfg) == []
