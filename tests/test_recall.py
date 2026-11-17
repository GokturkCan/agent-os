"""agentos recall: read-only SecondBrain search. Throwaway vaults only; the live vault is never touched.

Lives outside evals/ (protected). Run: .venv/bin/python -m pytest tests/test_recall.py
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentos import config
from agentos.knowledge import GateError, engine_cli
from agentos.recall import _terms, recall

ROOT = Path(__file__).resolve().parents[1]

PAGE = """---
type: project
title: "Orbit Planner"
status: developing
source_id: "src-orbit"
authority: primary
review_state: reviewed
---

# Orbit Planner

The planner schedules satellite passes. Current status: prototype implemented, blocker is ground-station latency.
"""


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def cfg():
    c = config.load()
    try:
        engine_cli(c)
    except GateError:
        pytest.skip("claude-obsidian engine not installed")
    return c


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    (v / "wiki/projects").mkdir(parents=True)
    (v / "wiki/meta/ledgers").mkdir(parents=True)
    (v / ".claude-obsidian.json").write_text(json.dumps({"role": "vault", "vault": ".", "schema":
                                                         "claude-obsidian.workspace.v1"}))
    (v / "wiki/projects/Orbit Planner.md").write_text(PAGE)
    (v / "wiki/meta/ledgers/source-ledger.json").write_text(json.dumps({"sources": {"src-orbit": {
        "origin": {"locator": ".raw/captured/abc.md"}, "authority": "primary",
        "review_status": "reviewed", "content_sha256": "abc", "pages": ["wiki/projects/Orbit Planner.md"]}}}))
    return v


def test_natural_language_query_finds_note_without_path(cfg, vault):
    res = recall(cfg, "What is the current status of my Orbit Planner project?", vault=vault)
    assert res["status"] == "ok"
    top = res["results"][0]
    assert top["path"] == "wiki/projects/Orbit Planner.md"
    assert top["provenance"]["frontmatter"]["source_id"] == "src-orbit"
    assert top["provenance"]["source_ledger"][0]["origin"] == ".raw/captured/abc.md"
    assert top["caution"] is None


def test_inflection_variants_match(cfg, vault):
    assert recall(cfg, "who is scheduling satellites", vault=vault)["status"] == "ok"
    assert "schedules" in _terms("scheduling") or "schedule" in _terms("scheduling")


def test_synthetic_source_is_flagged(cfg, vault):
    p = vault / "wiki/projects/Orbit Planner.md"
    p.write_text(PAGE.replace("authority: primary", "authority: synthetic"))
    assert recall(cfg, "orbit planner", vault=vault)["results"][0]["caution"]


def test_no_relevant_knowledge_fails_safe(cfg, vault):
    res = recall(cfg, "quantum banana zebra", vault=vault)
    assert res["status"] == "no_results" and res["results"] == []


def test_missing_vault_is_unavailable_not_exception(cfg, tmp_path):
    res = recall(cfg, "anything", vault=tmp_path / "nope")
    assert res["status"] == "unavailable" and res["reason"]


def test_vault_is_not_modified(cfg, vault):
    before = _tree_hash(vault)
    recall(cfg, "orbit planner status", vault=vault)
    recall(cfg, "nothing relevant here", vault=vault)
    assert _tree_hash(vault) == before          # no .vault-meta, no index, no edits
    assert not (vault / ".vault-meta").exists()


def test_cli_exit_codes(cfg):
    def run(q):
        return subprocess.run([sys.executable, "-m", "agentos.cli", "recall", q], capture_output=True,
                              text=True, cwd=ROOT)
    r = run("quantum banana zebra")
    assert r.returncode == 0 and json.loads(r.stdout)["status"] in ("no_results", "ok")
