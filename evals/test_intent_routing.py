"""Deterministic preload rule: clear repo-mutation requests force
`agent-os-orchestrate`; everything else is left to normal Hermes behaviour."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agentos import hermes_bridge as hb
from agentos.config import REPO_ROOT
from agentos.dispatch import WORKER_CONTEXT_ENV, dispatch
from agentos.intent import classify, decide
from agentos.taskstate import TaskStore

CORPUS = yaml.safe_load((REPO_ROOT / "evals" / "intent-corpus.yaml").read_text())
SKILL = "agent-os-orchestrate"


@pytest.mark.parametrize("text", CORPUS["force"])
def test_mutation_requests_are_forced(cfg, text):
    d = decide(cfg, text)
    assert d.force and d.skill == SKILL and d.verb and d.target, d


@pytest.mark.parametrize("text", CORPUS["no_force"])
def test_read_only_ambiguous_or_negated_requests_are_not_forced(cfg, text):
    d = decide(cfg, text)
    assert not d.force and d.skill is None, d


def test_corpus_has_no_false_positives_or_negatives(cfg):
    fp = [t for t in CORPUS["no_force"] if decide(cfg, t).force]
    fn = [t for t in CORPUS["force"] if not decide(cfg, t).force]
    assert (fp, fn) == ([], [])


def test_decision_is_inspectable_and_deterministic(cfg):
    a, b = decide(cfg, "fix this bug in the repository"), decide(cfg, "fix this bug in the repository")
    assert a == b and a.to_dict()["clause"] == "fix this bug in the repository"
    assert a.rules_version == cfg.routing["intent_rules"]["version"]
    assert "read-only" in decide(cfg, "explain this code").reason


def test_rule_is_config_driven(cfg):
    rules = {**cfg.routing["intent_rules"], "mutation_verbs": ["zap"]}
    assert not classify(rules, "fix this bug in the repository").force
    assert classify(rules, "zap this bug in the repository").force


# ------------------------------------------------- bypass / compatibility
def test_rule_can_only_select_the_orchestrate_skill_never_a_worker(cfg):
    rules = cfg.routing["intent_rules"]
    assert rules["skill"] == SKILL and SKILL not in hb.DIRECT_WORKER_SKILLS
    assert (REPO_ROOT / "skills" / SKILL / "SKILL.md").exists()
    for text in CORPUS["force"]:
        d = decide(cfg, text).to_dict()
        assert d["skill"] == SKILL and not {"worker", "provider", "argv"} & set(d)


def test_nested_dispatch_from_worker_context_still_refused(cfg, fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setenv(WORKER_CONTEXT_ENV, "x")
    res = dispatch(cfg, task_id="nest-1", task_type="coding", repo=fixture_repo, prompt="p", verify="true")
    assert res["exit_state"] == "unsafe" and res["status"] == "refused"


def _fake_hermes(tmp_path):
    f = tmp_path / "fake-hermes"
    f.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n')
    f.chmod(0o755)
    return f


def _wrapper(tmp_path, *args):
    # AGENTOS_BIN is faked so a forced request can never start a real dispatch here.
    fake = tmp_path / "fake-agentos"
    fake.write_text('#!/usr/bin/env bash\nif [ "$1" = mutate ]; then echo MUTATE; exit 0; fi\n'
                    f'exec {REPO_ROOT}/bin/agentos "$@"\n')
    fake.chmod(0o755)
    env = {**os.environ, "HERMES_BIN": str(_fake_hermes(tmp_path)), "AGENTOS_BIN": str(fake)}
    r = subprocess.run([str(REPO_ROOT / "bin" / "hermes-agentos"), *args], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def test_wrapper_routes_mutation_to_agentos_not_hermes(tmp_path):
    forced = _wrapper(tmp_path, "fix the failing test in the repo")
    assert forced == ["MUTATE"]
    plain = _wrapper(tmp_path, "explain this code")
    assert plain == ["chat", "-q", "explain this code"]


def test_explicit_preload_remains_compatible(tmp_path):
    out = _wrapper(tmp_path, "explain this code", "--skills", SKILL)       # user-supplied preload kept
    assert out == ["chat", "-q", "explain this code", "--skills", SKILL]
    cli = subprocess.run([sys.executable, "-m", "agentos.cli", "intent", "--text", "implement this feature"],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(cli)["hermes_args"] == ["--skills", SKILL]


# ------------------------------------------- timeout/retry/resume intact
def test_forced_request_then_dispatch_timeout_retry_resume(cfg, fixture_repo, tmp_path):
    from evals.test_timeouts import _fixing_runner, _go, _hanging_runner
    assert decide(cfg, "repair the failing tests").force
    assert _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)["status"] == "retryable"
    res = _go(cfg, fixture_repo, tmp_path, _fixing_runner)
    assert (res["status"], res["exit_state"]) == ("done", "success")
    assert TaskStore(cfg).get("tmo-task").state["timeouts"][0]["stage"] == "worker"


# ------------------------------------------------- clause-local negation
ACCEPTANCE = ("Fix the bug in this repository so the existing test passes. Make the smallest "
              "correct code change, run the tests to verify it, and do not modify the test.")


def test_real_acceptance_prompt_forces_orchestrate(cfg):
    d = decide(cfg, ACCEPTANCE)
    assert d.force and d.skill == SKILL and d.verb == "fix", d


@pytest.mark.parametrize("text", [
    "Fix the bug in this repository and do not modify the test.",
    "Update app.py, but do not change test_app.py.",
    "Repair the failing implementation; leave the tests untouched.",
    "Refactor this module and do not edit the config.",
])
def test_mutation_clause_survives_trailing_constraint(cfg, text):
    assert decide(cfg, text).force


@pytest.mark.parametrize("text", [
    "Do not modify the repository.",
    "Do not change the code; explain the bug.",
    "How do I fix this bug?",
    "Review this repository but do not modify anything.",
    "Find the likely cause.",
])
def test_negated_or_read_only_requests_stay_unforced(cfg, text):
    assert not decide(cfg, text).force
