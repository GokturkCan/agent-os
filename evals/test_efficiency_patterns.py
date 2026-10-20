"""R3.5 efficiency patterns: ContextGate / ToolPruner signal protection, WakeGate must-wake coverage, retrieval selection and
citation verification. Deterministic, offline, no model inference (a stub backend stands in for the neural paths)."""
import hashlib
import json
import tempfile
from pathlib import Path

import pytest
import yaml

from agentos import config as C
from agentos import contextgate as CG
from agentos import module_eval as M
from agentos import retrieval_select as R
from agentos import systemone as S
from agentos import toolpruner as TP
from agentos import wakegate as W

ROOT = Path(__file__).parents[1]
MOD = ROOT / "evals" / "data" / "modules"


def suite(name, split):
    return str(MOD / f"{name}-suite-v2-{split}.yaml")


# ------------------------------------------------------------------ fixtures are the frozen ones
def test_v2_fixtures_match_the_freeze_record():
    freeze = json.loads((ROOT / "audit" / "efficiency" / "fixtures-freeze.json").read_text())["files"]
    assert len(freeze) == 7
    for rel, sha in freeze.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel


# ------------------------------------------------------------------ ContextGate / ToolPruner
@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_contextgate_keeps_every_essential_fact_and_recovers_exactly(cfg, split):
    r = M.eval_contextgate(cfg, "none", suite("contextgate", split))
    assert r["false_drops"] == 0 and r["recovery_exact_all"] is True and r["model_calls"] == 0
    assert r["token_reduction"] > 0.5                      # still a real saving


@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_toolpruner_keeps_every_essential_line_and_recovers_exactly(cfg, split):
    r = M.eval_toolpruner(cfg, "none", suite("toolpruner", split))
    assert r["essential_lost"] == 0 and r["recovery_exact_all"] is True


def test_historical_v1_results_are_not_regressed(cfg):
    cg, tp = M.eval_contextgate(cfg, "none"), M.eval_toolpruner(cfg, "none")
    assert (cg["false_drops"], cg["essential_facts"]) == (0, 35) and cg["token_reduction"] >= 0.507
    assert (tp["essential_lost"], tp["essential_lines"]) == (0, 27) and tp["token_reduction"] >= 0.46
    assert M.eval_wakegate(cfg, "none")["false_negatives"] == 0


@pytest.mark.parametrize("line", [
    "ECONNREFUSED 127.0.0.1:5432", "Segmentation fault (core dumped)", "< HTTP/2 429 ", "worker-5c8   0/1   CrashLoopBackOff   14   31m",
    "ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "x509: certificate signed by unknown authority",
    "      Exit Code:    137", "Process exited with signal SIGSEGV", "not ok 14 - handles empty payload"])
def test_failure_signals_without_error_words_are_protected(line):
    assert CG.protected_lines(line, identifiers=False) == [0]            # both ContextGate and ToolPruner use this layer


@pytest.mark.parametrize("line", ["each event handled", "vacuum pass 3 completed", "the room is booked", "Zoom call moved", "batch 12 ok"])
def test_ordinary_words_are_not_protected(line):
    assert CG.protected_lines(line) == []


def test_identifiers_are_protected_for_contextgate_but_not_toolpruner():
    for line in ["introduced in commit 9fceb02a", "linked to ticket PAY-2291", "Created resource id=88213", "numpy-1.26.4 installed"]:
        assert CG.protected_lines(line) == [0], line
        assert not TP._protected(line), line
    assert CG.protected_lines("checkpoint 1234567 written") == []        # pure digits (timestamps/counters) are not hashes


def test_contextgate_store_still_refuses_the_vault(tmp_path):
    with pytest.raises(ValueError):
        CG.Store(CG.SECONDBRAIN / "inbox")


# ------------------------------------------------------------------ WakeGate
@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_every_must_wake_event_is_caught_by_a_rule_not_just_by_the_fallback(cfg, split):
    r = M.eval_wakegate(cfg, "none", suite("wakegate", split))
    assert r["false_negatives"] == 0 and r["must_wake_rule_coverage"] == 1.0


class AlwaysDefer:
    name = "always-defer"

    def decide(self, request):
        from agentos.systemone import Answer, Confidence, SystemOneResponse
        return SystemOneResponse((Answer("wake", W.DEFER, Confidence(0.9, "raw"), "backend-choice"),), False, "backend-choice", self.name)


@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_a_model_that_always_defers_cannot_suppress_a_must_wake_event(cfg, split):
    data = yaml.safe_load(Path(suite("wakegate", split)).read_text())
    for c in data["cases"]:
        if c["gold"] != "must_wake":
            continue
        ev = c["event"]
        e = W.Event(kind=ev["kind"], summary=ev.get("summary", ""), source=ev.get("source", ""), risk=ev.get("risk", "low"),
                    markers=tuple(ev.get("markers", ())), from_user=bool(ev.get("from_user")),
                    requires_approval=bool(ev.get("requires_approval")), deadline_minutes=ev.get("deadline_minutes"))
        v = W.gate(e, W.WaitState(c["waiting_for"]), AlwaysDefer())
        assert v.wake and not v.model_called and v.reason.startswith("rule:"), c["id"]


def test_benign_text_with_lookalike_substrings_does_not_trip_the_new_rules():
    for text in ["Zoom call moved to 15:00", "Room 5 is booked", "Total 503 items sorted"]:
        assert W.must_wake(W.Event(kind="calendar", summary=text)) is None, text


# ------------------------------------------------------------------ retrieval selection and citations
POOL = [R.Candidate("a", "Database backups run nightly and are kept for 35 days.", "n/a.md"),
        R.Candidate("b", "The backup of laptop photos is manual.", "n/b.md"),
        R.Candidate("c", "Quarterly planning is in the first week.", "n/c.md")]


def test_select_preserves_attribution_and_ignores_zero_overlap():
    sel = R.select("how long are database backups kept", POOL, k=3)
    assert sel[0].source_id == "a" and sel[0].sha256 == POOL[0].sha256 and sel[0].path == "n/a.md" and sel[0].rank == 1
    assert "c" not in {s.source_id for s in sel}
    assert R.select("zebra quantum", POOL) == []


def test_select_is_deterministic_and_rejects_duplicate_ids():
    assert R.select("backups", POOL) == R.select("backups", POOL)
    with pytest.raises(ValueError):
        R.select("x", POOL + [R.Candidate("a", "dup")])


class PickBackend:
    name = "pick"

    def __init__(self, choice):
        self.choice = choice

    def decide(self, request):
        from agentos.systemone import Answer, Confidence, SystemOneResponse
        return SystemOneResponse((Answer("passage", self.choice, Confidence(0.5, "raw"), "backend-choice"),), False, "backend-choice", self.name)


def test_neural_rerank_can_reorder_but_never_add_or_invent():
    base = [s.source_id for s in R.select("backup", POOL, 3)]
    re = R.select("backup", POOL, 3, backend=PickBackend(base[-1]))
    assert re[0].source_id == base[-1] and re[0].how == "neural-rerank" and {s.source_id for s in re} == set(base)
    assert [s.source_id for s in R.select("backup", POOL, 3, backend=PickBackend("c"))] == base      # "c" was not offered -> ignored
    assert [s.source_id for s in R.select("backup", POOL, 3, backend=S.NullBackend())] == base         # escalation keeps lexical order


def test_fabricated_citations_are_rejected():
    sel = R.select("how long are database backups kept", POOL, 1)
    assert [x.source_id for x in sel] == ["a"]
    got = {v.reason for v in R.verify_citations([
        {"source_id": "a", "quote": "kept for 35 days"}, {"source_id": "a", "quote": "kept for 90 days"},
        {"source_id": "zzz", "quote": "x"}, {"source_id": "c", "quote": "Quarterly planning"}, {"source_id": "a", "quote": " "},
        "garbage", {"source_id": 7, "quote": None}], POOL, sel)}
    assert got == {"supported", "quote_not_in_source", "unknown_source", "source_not_selected", "empty_quote"}
    ok = R.verify_citations([{"source_id": "a", "quote": "KEPT   for 35\ndays"}], POOL)
    assert ok[0].supported                                                  # whitespace/case-insensitive verbatim match


def test_retrieval_suite_has_zero_false_citation_accepts(cfg):
    r = M.eval_retrieval(cfg, "none")
    assert r["citation_false_accepts"] == 0 and r["citation_verdict_mismatches"] == 0 and M.acceptance(r)
    s = r["strategies"]
    assert s["lexical-bm25"]["all"]["recall@3"] >= s["naive-word-overlap"]["all"]["recall@3"]
    assert "unavailable" in r["embedding_selection"]


def test_new_modules_have_no_network_or_download_code():
    for mod in ("retrieval_select", "contextgate", "toolpruner", "wakegate"):
        src = (ROOT / "agentos" / f"{mod}.py").read_text()
        assert not any(w in src for w in ("import requests", "urllib", "socket", "http.client", "subprocess", "anthropic", "openai")), mod


# ------------------------------------------------------------------ production defaults
def test_production_defaults_unchanged(cfg):
    assert C.validate(cfg) == []
    assert cfg.routing["systemone"]["backend"] == "null" and cfg.models["tiers"]["fastgate"]["model"] is None
    assert cfg.systemone["activation"] == {"production_backends": [], "fastgate_models": []}


# ------------------------------------------------------------------ compat observability (additive)
def test_compat_trace_is_typed_and_contains_no_inputs():
    from agentos import systemone_compat as X
    body = {"state": "secret-looking task text", "questions": {"w": {"type": "choice", "instructions": "who?",
                                                                      "criteria": {"codex": "tests", "claude_code": None}}}}
    out = X.decide(body, ["claude_code", "codex"])
    assert out["answers"]["_escalation_0"]["reason"] == "no-backend"                  # existing shape unchanged
    t = out["trace"][0]
    assert set(t) == {"question", "escalated", "reason", "fallback", "latency_ms"}
    assert t["escalated"] is True and t["fallback"] == "deterministic-policy" and t["reason"] in S.REASON_CODES
    assert "secret-looking" not in json.dumps(out)
