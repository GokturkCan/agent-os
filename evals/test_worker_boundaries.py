"""Worker fallback boundaries: OpenCode fails closed; git push is stopped for every spelling.

Pre-release review findings M1/M2. The deny-pattern shapes below were validated live against a
throwaway local remote (2026-10-14): the legacy prefix patterns let `git -C . push`,
`/path/git push`, `git -c k=v push`, `sh -c 'git push'` and `git --no-pager push` through;
the wildcard patterns stopped all 12 push/remote-rewrite spellings. Everything here is local
and deterministic (no network, no worker is launched)."""
import copy
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agentos import capability_policy as CP
from agentos import capability_probes as P
from agentos import capability_registry as R
from agentos import config as C
from agentos import router, workers
from agentos.dispatch import WORKER_CONTEXT_ENV, dispatch
from agentos.permissions import PermissionDenied, WorkerSession
from agentos.workers import ENFORCED_WORKERS, build_launch, git_push_guard_env
from evals.test_timeouts import FIXED, PYTEST


def _cfg_with(cfg, mutate):
    data = copy.deepcopy(cfg.data)
    mutate(data)
    return C.Config(root=cfg.root, data=data)


# ------------------------------------------------------------ OpenCode fails closed
@pytest.mark.parametrize("profile", ["readonly", "coder"])
def test_opencode_launch_is_refused(cfg, tmp_path, profile):
    with pytest.raises(PermissionDenied):
        build_launch(cfg, WorkerSession.start(cfg, "opencode", profile), "p", tmp_path)


def test_opencode_refused_even_if_config_flag_is_flipped_back(cfg, tmp_path):
    reenabled = _cfg_with(cfg, lambda d: d["workers"]["workers"]["opencode"].update(status="available"))
    with pytest.raises(PermissionDenied, match="no launch adapter enforces the capability profile"):
        build_launch(reenabled, WorkerSession.start(reenabled, "opencode", "readonly"), "p", tmp_path)


def test_router_never_selects_opencode_even_if_reenabled(cfg):
    reenabled = _cfg_with(cfg, lambda d: d["workers"]["workers"]["opencode"].update(status="available"))
    for c in (cfg, reenabled):
        for health in ({}, {"workers": {"claude_code": False}}, {"workers": {"claude_code": False, "codex": False}},
                       {"providers": {"claude_subscription": False}}):
            d = router.route(c, {"type": "coding"}, health)
            assert d.worker != "opencode", (health, d.to_dict())
    d = router.route(reenabled, {"type": "coding"}, {"workers": {"claude_code": False, "codex": False}})
    assert d.worker is None and d.exit_state == "blocked"            # fail closed, not ambient execution
    assert any("opencode: launch adapter cannot enforce" in t for t in d.trace)


def test_fallback_still_reaches_codex_and_claude(cfg):
    assert router.route(cfg, {"type": "coding"}).worker == "claude_code"
    d = router.route(cfg, {"type": "coding"}, {"workers": {"claude_code": False}})
    assert (d.provider, d.worker) == ("codex_subscription", "codex")
    d = router.route(cfg, {"type": "coding"}, {"providers": {"claude_subscription": False}})
    assert (d.provider, d.worker) == ("codex_subscription", "codex")


def test_every_launchable_worker_either_enforces_or_is_refused(cfg, tmp_path):
    launchable = [n for n, s in cfg.workers["workers"].items() if s.get("launch")]
    assert set(ENFORCED_WORKERS) <= set(launchable)
    for name in launchable:
        s = WorkerSession(cfg, name, cfg.workers["workers"][name].get("default_profile", "readonly"))
        if name in ENFORCED_WORKERS:
            assert build_launch(cfg, s, "p", tmp_path)["env"]          # carries the push guard
        else:
            with pytest.raises(PermissionDenied):
                build_launch(_cfg_with(cfg, lambda d: d["workers"]["workers"][name].update(status="available")),
                             s, "p", tmp_path)


def test_registry_keeps_opencode_registered_but_never_eligible(cfg):
    reg = R.load(cfg)
    assert reg.get("opencode").adoption == "disabled" and "opencode" in {p.id for p in reg.executors()}
    ok = P.static_probes(reg, default={"available": "present", "health": "healthy", "auth": "present"})
    pl = CP.plan(reg, CP.CapabilityRequest(required=("code.edit",)), ok)
    assert "opencode" not in pl.eligible_executors and pl.eligible_workers == ["claude_code", "codex"]
    assert pl.rejected_executors["opencode"].reasons == ["policy-blocked"]
    both_down = P.static_probes(reg, states={"claude-code": {"available": "absent"}, "codex": {"available": "absent"}},
                                default={"available": "present", "health": "healthy", "auth": "present"})
    blocked = CP.plan(reg, CP.CapabilityRequest(required=("code.edit",)), both_down)
    assert blocked.status == "blocked" and blocked.executor is None


# ------------------------------------------------------------ deny list (Claude command filter)
PUSH_PATTERNS = ("Bash(git push:*)", "Bash(git remote:*)", "Bash(*git*push*)", "Bash(*git*remote*)")


@pytest.mark.parametrize("profile", ["readonly", "coder", "reviewer"])
def test_claude_denies_wildcard_push_and_remote_forms_for_every_profile(cfg, tmp_path, profile):
    launch = build_launch(cfg, WorkerSession.start(cfg, "claude_code", profile), "p", tmp_path)
    denied = launch["argv"][launch["argv"].index("--disallowedTools") + 1].split(",")
    for pat in PUSH_PATTERNS:
        assert pat in denied, pat
    allowed = launch["argv"][launch["argv"].index("--allowedTools") + 1].split(",")
    assert not [a for a in allowed if "push" in a or "remote" in a]


# ------------------------------------------------------------ structural git guard (all enforced workers)
@pytest.fixture
def repo_with_remote(tmp_path):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@l", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@l"}
    bare, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work.mkdir()
    for args in (["init", "-q", "-b", "main"], ["remote", "add", "origin", str(bare)]):
        subprocess.run(["git", *args], cwd=work, check=True, env=env)
    (work / "a.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=work, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=work, check=True, env=env)
    return work, bare, env


def _refs(bare):
    return subprocess.run(["git", "-C", str(bare), "for-each-ref", "--format=%(refname)"],
                          capture_output=True, text=True).stdout.split()


GIT = shutil.which("git")
PUSH_SPELLINGS = [
    "git push origin HEAD:refs/heads/x",
    "git -C . push origin HEAD:refs/heads/x",
    "command git push origin HEAD:refs/heads/x",
    f"{GIT} push origin HEAD:refs/heads/x",
    "env git push origin HEAD:refs/heads/x",
    "git -c core.pager=cat push origin HEAD:refs/heads/x",
    "sh -c 'git push origin HEAD:refs/heads/x'",
    "git --no-pager push origin HEAD:refs/heads/x",
    "git push origin --force HEAD:refs/heads/x",
    "git push {bare} HEAD:refs/heads/x",                      # raw path, not a configured remote
]


@pytest.mark.parametrize("worker", ["claude_code", "codex"])
@pytest.mark.parametrize("cmd", PUSH_SPELLINGS)
def test_equivalent_push_spellings_are_stopped_by_the_guard(cfg, repo_with_remote, worker, cmd):
    work, bare, env = repo_with_remote
    launch = build_launch(cfg, WorkerSession.start(cfg, worker, "coder"), "p", work)
    r = subprocess.run(["sh", "-c", cmd.format(bare=bare)], cwd=work, capture_output=True, text=True,
                       env={**env, **launch["env"]})
    assert r.returncode != 0 and "human-only" in r.stderr, (cmd, r.stderr)
    assert _refs(bare) == []                                 # nothing reached the remote
    assert subprocess.run(["git", "config", "--local", "remote.origin.url"], cwd=work, capture_output=True,
                          text=True).stdout.strip() == str(bare)   # remotes untouched


def test_unguarded_environment_would_have_pushed(repo_with_remote):
    """Control: without the guard env the same push succeeds, so the tests above are meaningful."""
    work, bare, env = repo_with_remote
    r = subprocess.run(["git", "-C", ".", "push", "origin", "HEAD:refs/heads/x"], cwd=work, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0 and _refs(bare) == ["refs/heads/x"]


def test_normal_local_git_work_is_unaffected_by_the_guard(cfg, repo_with_remote):
    work, bare, env = repo_with_remote
    genv = {**env, **build_launch(cfg, WorkerSession.start(cfg, "codex", "coder"), "p", work)["env"]}
    (work / "b.txt").write_text("y")
    for args in (["status", "--porcelain"], ["add", "-A"], ["commit", "-qm", "worker commit"],
                 ["log", "--oneline"], ["diff", "HEAD~1"], ["branch", "-a"]):
        assert subprocess.run(["git", *args], cwd=work, env=genv, capture_output=True).returncode == 0, args


def test_guard_env_composes_with_existing_git_config_env():
    e = git_push_guard_env({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "a.b", "GIT_CONFIG_VALUE_0": "1"})
    assert e["GIT_CONFIG_COUNT"] == "3" and e["GIT_CONFIG_KEY_2"] == "core.hooksPath"
    assert "GIT_CONFIG_KEY_0" not in e                       # existing entries are preserved, not overwritten
    assert git_push_guard_env({"GIT_CONFIG_COUNT": "junk"})["GIT_CONFIG_KEY_0"] == "core.hooksPath"


def test_missing_or_non_executable_guard_hook_fails_closed(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(workers, "GIT_GUARD_HOOKS", tmp_path)                       # no hook present
    with pytest.raises(PermissionDenied, match="guard hook"):
        build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"), "p", tmp_path)
    (tmp_path / "pre-push").write_text("#!/bin/sh\nexit 1\n")                       # present, not executable
    with pytest.raises(PermissionDenied, match="guard hook"):
        build_launch(cfg, WorkerSession.start(cfg, "codex", "coder"), "p", tmp_path)


def test_guard_hook_is_tracked_executable_and_always_fails():
    hook = Path(workers.GIT_GUARD_HOOKS) / "pre-push"
    assert os.access(hook, os.X_OK)
    assert subprocess.run([str(hook)], capture_output=True).returncode == 1
    mode = subprocess.run(["git", "ls-files", "-s", str(hook)], capture_output=True, text=True,
                          cwd=C.REPO_ROOT).stdout.split()[:1]
    assert mode in ([], ["100755"])                          # executable bit is what git records (or untracked yet)


# ------------------------------------------------------------ dispatch keeps the guard
def test_dispatch_passes_guard_and_worker_context_env_to_the_runner(cfg, fixture_repo, tmp_path):
    seen = []

    def runner(launch, **kw):
        seen.append(dict(launch["env"]))
        (Path(launch["cwd"]) / "calc.py").write_text(FIXED)
        return {"returncode": 0, "latency_ms": 1.0}
    res = dispatch(cfg, task_id="guard-task", task_type="coding", repo=fixture_repo, prompt="fix add()",
                   verify=PYTEST, runner=runner, worktree_root=tmp_path / "wts")
    assert res["exit_state"] == "success"
    assert seen[0][WORKER_CONTEXT_ENV] == "guard-task"
    assert seen[0]["GIT_CONFIG_KEY_0"] == "core.hooksPath" and seen[0]["GIT_CONFIG_VALUE_0"].endswith("githooks")
