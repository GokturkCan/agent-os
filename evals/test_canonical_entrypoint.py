"""bin/hermes-agentos is the canonical Agent OS -> Hermes entrypoint; bare
`hermes chat` stays possible but is visibly non-canonical."""
import os
import re
import subprocess

import pytest

from agentos import health, hermes_bridge as hb
from agentos.config import REPO_ROOT
from agentos.dispatch import WORKER_CONTEXT_ENV, dispatch

SKILL = "agent-os-orchestrate"


ACCEPTANCE = ("Fix the bug in this repository so the existing test passes. Make the smallest "
              "correct code change, run the tests to verify it, and do not modify the test.")


def _wrapper(tmp_path, *args, env=None):
    """Run the wrapper with fake hermes + fake agentos; return (hermes_argv, agentos_argv)."""
    logs = {}
    for name in ("hermes", "agentos"):
        log = tmp_path / f"{name}.log"
        fake = tmp_path / f"fake-{name}"
        fake.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > {log}\n')
        fake.chmod(0o755)
        logs[name] = log
    real = hb.CANONICAL_ENTRYPOINT.parent / "agentos"
    # intent must stay real; only `mutate` is faked
    shim = tmp_path / "agentos-shim"
    shim.write_text(f'#!/usr/bin/env bash\nif [ "$1" = mutate ]; then exec {tmp_path}/fake-agentos "$@"; fi\n'
                    f'exec {real} "$@"\n')
    shim.chmod(0o755)
    r = subprocess.run([str(hb.CANONICAL_ENTRYPOINT), *args], capture_output=True, text=True, cwd=tmp_path,
                       env={**os.environ, "HERMES_BIN": str(tmp_path / "fake-hermes"),
                            "AGENTOS_BIN": str(shim), **(env or {})})
    assert r.returncode == 0, r.stderr
    read = lambda n: logs[n].read_text().splitlines() if logs[n].exists() else None
    return read("hermes"), read("agentos")


@pytest.mark.parametrize("text,forced", [
    ("fix this bug in the repository", True),
    ("implement this feature in the codebase", True),
    ("explain this code", False),
    ("research this library", False),
    ("fix it", False),
    (ACCEPTANCE, True),
])
def test_canonical_wrapper_gate(tmp_path, text, forced):
    hermes, agentos = _wrapper(tmp_path, text)
    if forced:
        assert hermes is None, "force=true must never start normal Hermes"
        assert agentos[:1] == ["mutate"] and agentos[agentos.index("--text") + 1] == text
    else:
        assert agentos is None
        assert hermes == ["chat", "-q", text]


def test_mutation_forwards_prompt_cwd_and_verify(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _, agentos = _wrapper(tmp_path, ACCEPTANCE, env={"AGENTOS_REPO": str(repo), "AGENTOS_VERIFY": "python3 -m pytest -q"})
    assert agentos[agentos.index("--text") + 1] == ACCEPTANCE
    assert agentos[agentos.index("--repo") + 1] == str(repo)
    assert agentos[agentos.index("--verify") + 1] == "python3 -m pytest -q"


def test_mutation_defaults_repo_to_cwd(tmp_path):
    _, agentos = _wrapper(tmp_path, ACCEPTANCE)
    assert agentos[agentos.index("--repo") + 1] == str(tmp_path)


def test_read_only_extra_args_still_forwarded(tmp_path):
    hermes, _ = _wrapper(tmp_path, "explain this code", "--model", "x")
    assert hermes == ["chat", "-q", "explain this code", "--model", "x"]


def test_agent_os_files_use_no_bare_hermes_invocations():
    assert hb.find_bare_invocations() == []


def test_detector_flags_bare_calls_and_allows_marked_docs(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.sh").write_text('hermes chat -q "fix the repo"\n')
    (tmp_path / "README.md").write_text("`hermes chat` is non-canonical here\n")
    assert hb.find_bare_invocations(tmp_path) == ["scripts/x.sh:1"]


def test_wrapper_is_the_only_operational_caller_of_hermes_chat():
    assert re.search(r"\bchat\b", hb.CANONICAL_ENTRYPOINT.read_text())
    assert hb.entrypoint_status()[0]


def test_bare_chat_documented_and_visible_in_health():
    doc = (REPO_ROOT / "docs" / "hermes-integration.md").read_text()
    assert "bin/hermes-agentos" in doc and "bare `hermes chat` is non-canonical" in doc
    if hb.available():
        names = {r["check"]: r for r in health.run_checks()}
        assert names["hermes.canonical_entrypoint"]["status"] == "PASS"
        assert names["hermes.bare_invocations"]["status"] == "PASS"
        assert names["hermes.bare_chat_noncanonical"]["status"] == "INFO"


def test_direct_worker_bypass_still_blocked(cfg, fixture_repo, monkeypatch):
    assert not set(hb.DIRECT_WORKER_SKILLS) & {SKILL}
    monkeypatch.setenv(WORKER_CONTEXT_ENV, "x")
    res = dispatch(cfg, task_id="bypass-1", task_type="coding", repo=fixture_repo, prompt="p", verify="true")
    assert res["status"] == "refused"
    assert cfg.workers["workers"]["hermes_delegation"]["selectable"] is False


def test_timeout_retry_resume_unchanged(cfg, fixture_repo, tmp_path):
    from evals.test_timeouts import _fixing_runner, _go, _hanging_runner
    assert _go(cfg, fixture_repo, tmp_path, _hanging_runner(), timeout=1)["status"] == "retryable"
    assert _go(cfg, fixture_repo, tmp_path, _fixing_runner)["exit_state"] == "success"


# ---- mutate: the structural branch itself (real dispatch(), fake runner never needed for dry-run)
def test_mutate_cli_dry_run_reaches_dispatch(fixture_repo):
    r = subprocess.run([str(hb.CANONICAL_ENTRYPOINT.parent / "agentos"), "mutate", "--text", ACCEPTANCE,
                        "--repo", str(fixture_repo), "--verify", "true", "--dry-run"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = __import__("json").loads(r.stdout)
    assert out["task_id"].startswith("hermes-") and out["worker"]


def test_mutate_refuses_non_mutation_request(fixture_repo):
    r = subprocess.run([str(hb.CANONICAL_ENTRYPOINT.parent / "agentos"), "mutate", "--text", "explain this code",
                        "--repo", str(fixture_repo), "--verify", "true"], capture_output=True, text=True)
    assert r.returncode == 2 and "normal Hermes" in r.stderr


def test_mutate_passes_prompt_repo_verify_to_dispatch(cfg, fixture_repo, monkeypatch):
    from agentos import mutate
    seen = {}
    monkeypatch.setattr(mutate, "dispatch", lambda c, **kw: seen.update(kw) or {"exit_state": "success"})
    mutate.run(cfg, ACCEPTANCE, fixture_repo, verify="true")
    assert seen["prompt"] == ACCEPTANCE and seen["repo"] == fixture_repo.resolve()
    assert seen["task_type"] == "coding" and seen["verify"] == "true"


def test_mutate_without_verify_is_blocked_not_hermes(cfg, tmp_path, monkeypatch):
    from agentos import mutate
    monkeypatch.setattr(mutate, "dispatch", lambda *a, **k: pytest.fail("must not dispatch"))
    res = mutate.run(cfg, ACCEPTANCE, tmp_path)
    assert res["status"] == "not_dispatched"


def test_detect_verify(tmp_path):
    from agentos.mutate import detect_verify
    assert detect_verify(tmp_path) is None
    (tmp_path / "test_x.py").write_text("")
    assert detect_verify(tmp_path) == "python3 -m unittest -v"
    (tmp_path / "conftest.py").write_text("")
    assert detect_verify(tmp_path) == "python3 -m pytest -q"
