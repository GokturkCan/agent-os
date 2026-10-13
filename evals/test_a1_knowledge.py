"""Acceptance 1 — KNOWLEDGE (+ retrieval/provenance family).

ingest sample evidence -> raw preserved -> canonical page via reviewed
transaction -> provenance survives -> no silent overwrite.
"""
import hashlib
import json

import pytest

from agentos.knowledge import GateError, ingest_source_writes, utc_today

TODAY = utc_today()


def _stage(vault, name, text):
    p = vault.root / "inbox" / name
    p.write_text(text)
    return p


def _ingest(vault, text="# Pytest\n\nDeterministic test results beat LLM judgement.\n"):
    _stage(vault, "evidence.md", text)
    cap = vault.capture(["inbox/evidence.md"])
    assert cap["status"] == "applied"
    sha = hashlib.sha256(text.encode()).hexdigest()
    raw_rel = f".raw/captured/{sha}.md"
    b = ingest_source_writes(vault, sha, raw_rel, "Pytest Evidence",
                             "Deterministic test results should be preferred.",
                             {"clm-deterministic-first": "Deterministic checks precede LLM judgement."},
                             authority="primary", today=TODAY)
    meta = vault.propose("ingest-pytest", "ingest", b["writes"], proposer="claude_code",
                         source_manifest_updates=b["source_manifest_updates"],
                         address_requests=b["address_requests"])
    return sha, raw_rel, b, meta


def test_raw_evidence_preserved_and_create_only(vault):
    text = "# Pytest\n\nDeterministic test results beat LLM judgement.\n"
    _stage(vault, "evidence.md", text)
    vault.capture(["inbox/evidence.md"])
    sha = hashlib.sha256(text.encode()).hexdigest()
    raw = vault.root / ".raw" / "captured" / f"{sha}.md"
    assert raw.read_text() == text                       # byte-identical evidence
    assert vault.capture(["inbox/evidence.md"])["status"] == "noop"   # re-capture is idempotent


def test_canonical_write_requires_independent_human_approved_review(vault):
    sha, raw_rel, b, meta = _ingest(vault)
    page = vault.root / b["page"]
    assert not page.exists()
    with pytest.raises(GateError, match="no approval record"):
        vault.apply("ingest-pytest")
    with pytest.raises(GateError, match="independent"):
        vault.approve("ingest-pytest", "claude_code", meta["approval_sha256"], "human:test")
    with pytest.raises(GateError, match="hash"):
        vault.approve("ingest-pytest", "reviewer", "0" * 64, "human:test")
    with pytest.raises(GateError, match="human approval"):
        vault.approve("ingest-pytest", "reviewer", meta["approval_sha256"], "")
    assert not page.exists()


def test_reviewed_ingest_creates_canonical_knowledge_with_provenance(vault):
    sha, raw_rel, b, meta = _ingest(vault)
    vault.approve("ingest-pytest", "codex_reviewer", meta["approval_sha256"], "human:acceptance-test")
    res = vault.apply("ingest-pytest")
    assert res["status"] == "complete"
    page = (vault.root / b["page"]).read_text()
    assert sha in page and b["source_id"] in page
    sl = json.loads(vault.read("wiki/meta/ledgers/source-ledger.json"))
    src = sl["sources"][b["source_id"]]
    assert src["content_sha256"] == sha and src["origin"]["locator"] == raw_rel
    assert (vault.root / raw_rel).exists()                # chain page -> ledger -> raw intact
    cl = json.loads(vault.read("wiki/meta/ledgers/claim-ledger.json"))
    assert cl["claims"]["clm-deterministic-first"]["evidence"][0]["source_id"] == b["source_id"]
    manifest = json.loads(vault.read(".raw/.manifest.json"))
    assert manifest["sources"][sha]["source_id"] == b["source_id"]
    assert res["lint"]["issues_found"] == 0


def test_no_silent_overwrite_when_target_changed_after_proposal(vault):
    sha, raw_rel, b, meta = _ingest(vault)
    vault.approve("ingest-pytest", "reviewer", meta["approval_sha256"], "human:acceptance-test")
    log = vault.root / "wiki" / "log.md"
    human_edit = log.read_text() + "\n- a concurrent human edit\n"
    log.write_text(human_edit)                            # canonical file changes after review
    with pytest.raises(GateError):
        vault.apply("ingest-pytest")
    assert log.read_text() == human_edit                  # human edit preserved
    assert not (vault.root / b["page"]).exists()          # nothing partially applied


def test_proposals_cannot_target_raw_or_meta(vault):
    for path in (".raw/captured/x.md", ".vault-meta/x", "inbox/x.md"):
        with pytest.raises(GateError, match="only target wiki"):
            vault.propose(f"bad-{abs(hash(path))}", "ingest",
                          [{"path": path, "mode": "create", "content": "x"}], proposer="w")


def test_live_secondbrain_healthy_readonly(cfg):
    """Retrieval/health against the LIVE vault — read-only engine calls."""
    from agentos.knowledge import Vault
    v = Vault(cfg)
    assert v.doctor()["ok"] is True
    assert v.lint()["summary"]["issues_found"] == 0
