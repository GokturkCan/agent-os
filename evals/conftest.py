"""Shared fixtures. Every test runs against temporary state/telemetry dirs and
a throwaway fixture vault — never the live ~/SecondBrain or state/."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from agentos import config as C
from agentos.knowledge import Vault, engine_cli


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENTOS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    monkeypatch.setenv("AGENTOS_RESOURCE_STATE", str(tmp_path / "state" / "resources.json"))
    monkeypatch.delenv("AGENTOS_VAULT", raising=False)
    yield


@pytest.fixture(scope="session")
def cfg():
    return C.load()


def _engine(*args, cwd):
    r = subprocess.run(["python3", str(engine_cli(C.load())), *args], capture_output=True,
                       text=True, cwd=cwd)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture
def vault(tmp_path, cfg):
    """A fresh claude-obsidian vault created by the engine's own init."""
    root = tmp_path / "vault"
    plan = _engine("init", str(root), cwd=tmp_path)
    _engine("init", str(root), "--apply", "--operation-id", plan["operation"]["operation_id"],
            "--generated-at", plan["generated_at"],
            "--approved-plan-sha256", plan["approved_plan_sha256"], cwd=tmp_path)
    return Vault(cfg, root=root, state_dir=tmp_path / "kstate")


@pytest.fixture
def fixture_repo(tmp_path):
    """Small git repo with one failing test (the coding acceptance target)."""
    repo = tmp_path / "calc"
    repo.mkdir()
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b  # bug\n")
    (repo / "test_calc.py").write_text(textwrap.dedent("""
        from calc import add
        def test_add():
            assert add(2, 3) == 5
        def test_add_negative():
            assert add(-1, 1) == 0
    """))
    env = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@localhost",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@localhost"}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "fixture: failing add"]):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    return repo


def git_env():
    return {**os.environ, "GIT_AUTHOR_NAME": "agentos-worker", "GIT_AUTHOR_EMAIL": "worker@localhost",
            "GIT_COMMITTER_NAME": "agentos-worker", "GIT_COMMITTER_EMAIL": "worker@localhost"}
