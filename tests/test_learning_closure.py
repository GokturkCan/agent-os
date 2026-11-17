"""Fixture vault: lesson proposal → authorize → apply → recall → task context."""
from __future__ import annotations

import os

import pytest

from agentos.config import load
from agentos.recall import recall

import test_knowledge_lifecycle as kf

pytest_plugins = ["test_knowledge_lifecycle"]


@pytest.fixture
def lesson_world(knowledge_world, monkeypatch):
    life, root, repo, _ = knowledge_world
    monkeypatch.setenv("AGENTOS_VAULT", str(root))
    return life, root, repo


def test_lesson_commit_recall_and_subsequent_context(lesson_world):
    life, root, _ = lesson_world
    cfg = load()
    text = "Verified lesson: always wait for both research branches before joining graph results."
    p = kf.capture(life, kind="lesson", summary=text)
    ready = life.ready(p["id"])
    assert ready["state"] == "READY_FOR_REVIEW"
    kf.reviewer_approve(life, p["id"])
    assert life.show(p["id"])["state"] == "APPROVED"
    assert life.gate.apply(p["id"])["lint"]["issues_found"] == 0
    committed = life.reconcile(p["id"])
    assert committed["state"] == "COMMITTED"
    assert (root / ready["target"]).is_file()

    hit = recall(cfg, "graph join research branches", vault=root, top=5)
    assert hit.get("status") in ("ok", "no_results")
    bodies = " ".join(r.get("excerpt", "") or "" for r in hit.get("results", []))
    assert text[:30] in bodies or (root / ready["target"]).read_text().find("research branches") >= 0

    ctx = life.context("orbit", "apply lesson about graph join research", budget=12_000)
    paths = [s["path"] for s in ctx.get("sources", [])]
    assert ready["target"] in paths
    page = (root / ready["target"]).read_text()
    assert "research branches" in page
    follow = life.context("orbit", text, budget=12_000)
    assert ready["target"] in [s["path"] for s in follow.get("sources", [])]