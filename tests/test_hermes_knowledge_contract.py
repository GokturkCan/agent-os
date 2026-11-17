"""Hermes knowledge contract: verified capture and where-stopped."""
from __future__ import annotations

import re

import pytest

from agentos.config import load
from agentos.hermes_knowledge import capture_remember, verify_proposal_on_disk, where_stopped

pytest_plugins = ["test_knowledge_lifecycle", "test_project_workflow"]


def test_verify_rejects_fabricated_proposal_id(knowledge_world):
    life, *_ = knowledge_world
    assert verify_proposal_on_disk(life, "kp-deadbeefdeadbeefdeadbeef") is False
    assert verify_proposal_on_disk(life, "not-an-id") is False


def test_remember_creates_verified_draft(knowledge_world):
    life, *_ = knowledge_world
    out = capture_remember(
        life,
        project_query="orbit",
        text="Prefer bounded latency over optimality for scheduling windows.",
        session="pytest-remember",
    )
    assert out["status"] == "captured"
    assert out["verified_on_disk"] is True
    assert re.fullmatch(r"kp-[a-f0-9]{24}", out["proposal_id"])
    assert life.show(out["proposal_id"])["state"] == "DRAFT"


def test_remember_refused_without_verification(knowledge_world, monkeypatch):
    life, *_ = knowledge_world
    monkeypatch.setattr(
        "agentos.hermes_knowledge.verify_proposal_on_disk",
        lambda _life, _pid: False,
    )
    out = capture_remember(life, project_query="orbit", text="Should not count as success.", session="t")
    assert out["status"] == "refused"
    assert out["verified_on_disk"] is False


def test_where_stopped_returns_authoritative_status(project_world):
    cfg, life, _, repo, _ = project_world
    out = where_stopped(cfg, life, project_query="orbit", repo=str(repo))
    assert out["status"] == "ok"
    assert out["project_status"]["schema"] == "agentos.project-status.v1"
    assert out["continuation"]["schema"] == "agentos.continuation-context.v1"
    assert "recall" in out