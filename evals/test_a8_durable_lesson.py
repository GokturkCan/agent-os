"""Acceptance 8 — DURABLE LESSON + controlled self-improvement gate."""
import hashlib
import json

import pytest

from agentos import telemetry
from agentos.knowledge import GateError, utc_today
from agentos.selfimprove import (Candidate, GateViolation, compute_manifest, lesson_writes,
                                 verify_manifest, write_lesson_candidate)


def test_run_produces_lesson_that_reaches_wiki_only_through_gate(vault):
    run = telemetry.record(task_type="coding", worker="codex", exit_state="no_progress",
                           notes="retried same flaky fix 3x")
    cand = write_lesson_candidate(vault.root, run, "Flaky Test Triage",
                                  "When a fix is retried without a changed progress signal, stop "
                                  "and quarantine the flaky test before further attempts.",
                                  [f"telemetry {run['run_id']}", "exit_state=no_progress"])
    assert cand.parent == vault.root / "inbox" / "lessons"
    assert not (vault.root / "wiki" / "concepts" / "Flaky Test Triage.md").exists()

    rel = str(cand.relative_to(vault.root))
    vault.capture([rel])
    sha = hashlib.sha256(cand.read_bytes()).hexdigest()
    raw_rel = f".raw/captured/{sha}.md"
    assert (vault.root / raw_rel).exists()

    writes = lesson_writes(vault, sha, raw_rel, "Flaky Test Triage", "Stop and quarantine.",
                           run["run_id"], utc_today())
    meta = vault.propose("lesson-flaky", "ingest", writes, proposer="codex")
    with pytest.raises(GateError):
        vault.apply("lesson-flaky")                       # proposal alone never lands
    vault.approve("lesson-flaky", "claude_code", meta["approval_sha256"], "human:lesson-review")
    assert vault.apply("lesson-flaky")["status"] == "complete"
    page = (vault.root / "wiki" / "concepts" / "Flaky Test Triage.md").read_text()
    assert run["run_id"] in page and sha in page          # provenance: run -> evidence -> page


def _cand(tmp_path, cid="c1"):
    return Candidate.propose(tmp_path / "si", cid, producer="codex", rationale="tune budget",
                             lesson_ref="Flaky Test Triage")


def test_candidate_touching_judge_or_heldout_is_rejected(tmp_path):
    for path in ("evals/test_a5_provider_failure.py", "config/permissions.yaml",
                 "config/promotion.yaml", "agentos/selfimprove.py"):
        c = _cand(tmp_path, f"c-{abs(hash(path))}")
        with pytest.raises(GateViolation):
            c.isolate("agentos/cand", ["config/routing.yaml", path])
        assert c.rec["stage"] == "rejected"


def test_full_gate_sequence_and_independence(tmp_path):
    c = _cand(tmp_path)
    with pytest.raises(GateViolation):
        c.judge("claude_code", True, "")                   # cannot skip isolation/eval
    c.isolate("agentos/cand", ["config/routing.yaml"])
    assert c.heldout_eval(True, "all passed", manifest_drift=[])
    with pytest.raises(GateViolation, match="independent"):
        c.judge("codex", True, "self-review")
    assert c.judge("claude_code", True, "ok")
    assert c.canary(True, "canary ok")
    with pytest.raises(GateViolation, match="human"):
        c.promote("")
    c.promote("human:merge-approval")
    assert c.rec["stage"] == "promoted"
    assert [h["stage"] for h in c.rec["history"]] == [
        "proposed", "isolated", "heldout_eval", "judged", "canary", "promoted"]


def test_canary_failure_rolls_back_and_drift_invalidates(tmp_path):
    c = _cand(tmp_path)
    c.isolate("b", ["config/routing.yaml"])
    c.heldout_eval(True, "ok", [])
    c.judge("claude_code", True, "ok")
    assert c.canary(False, "latency regression") is False
    assert c.rec["stage"] == "rolled_back"
    d = _cand(tmp_path, "c2")
    d.isolate("b", ["config/routing.yaml"])
    with pytest.raises(GateViolation, match="drift"):
        d.heldout_eval(True, "ok", manifest_drift=["evals/test_a1_knowledge.py"])


def test_repo_protected_manifest_matches():
    """The reviewed hashes of judges/held-out evals/policy must match the tree."""
    assert verify_manifest() == [], "protected files changed without manifest review"
    assert "config/permissions.yaml" in compute_manifest()
