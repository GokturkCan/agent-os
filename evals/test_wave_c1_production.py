"""Wave C1 production pipeline (task-scoped skill delivery, deterministic UI selection).

Deterministic, offline, no model call, no network, no credential read, no host config touched. Gate evidence that
needs a live worker or a browser is NOT here (see audit/wave-c1/acceptance-matrix.md for which gates are open)."""
import dataclasses
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agentos import capability_policy as CP
from agentos import capability_registry as R
from agentos import skill_delivery as SD
from agentos.config import REPO_ROOT
from agentos.dispatch import dispatch

OK = {"available": "present", "health": "healthy", "auth": "present"}
IDS = ["claude-code", "codex", "opencode", "serena", "context7", "playwright", "taste-skill",
       "frontend-design", "ui-ux-pro-max"]
OVERRIDES = {pid: dict(OK) for pid in IDS}
TASTE = REPO_ROOT / "third_party" / "taste-skill" / "skill"


def _activated(cfg):
    reg = R.load(cfg)
    reg.providers["taste-skill"] = dataclasses.replace(reg.providers["taste-skill"], adoption="adopted")
    return reg


@pytest.fixture
def reg(cfg):
    return R.load(cfg)


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """A throwaway copy of the lock + vendored tree that skill_delivery is pointed at (never the real one)."""
    dst = tmp_path / "repo"
    (dst / "scripts" / "runtime").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "scripts/runtime/skills.lock.json", dst / "scripts/runtime/")
    shutil.copytree(REPO_ROOT / "third_party/taste-skill", dst / "third_party/taste-skill")
    monkeypatch.setattr(SD, "REPO", dst)
    return dst


# ------------------------------------------------------------ registry facts (gate 7: deterministic selection)
def test_registry_records_are_truthful_and_inert(reg):
    t = reg.get("taste-skill")
    assert (t.kind, t.adoption, t.config_ref) == ("skill", "benchmark", "skills.taste_skill")
    assert [reg.get(i).adoption for i in ("frontend-design", "ui-ux-pro-max")] == ["future", "future"]
    assert "ui.art_direction" in reg.capabilities and "ui.visual_qa" in reg.capabilities


def test_task_type_mapping_is_registry_data_not_inference(cfg, reg):
    assert CP.resolve_required(reg, (), "ui_design") == ("code.edit", "code.test", "ui.art_direction", "ui.visual_qa")
    assert CP.resolve_required(reg, (), "coding") == ("code.edit", "code.test")      # coding unchanged


def test_ui_design_fails_closed_until_taste_is_activated(cfg, reg):
    pl = CP.plan_for(cfg, task_type="ui_design", overrides=OVERRIDES, registry=reg)
    assert pl.status == "blocked" and pl.eligible_executors == []
    assert "capability-missing" in pl.rejected_executors["claude-code"].reasons


def test_activated_plan_is_deterministic_taste_first_claude_only(cfg):
    reg = _activated(cfg)
    plans = [CP.plan_for(cfg, task_type="ui_design", overrides=OVERRIDES, registry=reg) for _ in range(3)]
    assert len({json.dumps(CP.telemetry_payload(p), sort_keys=True) for p in plans}) == 1
    pl = plans[0]
    assert pl.status == "selected" and pl.eligible_executors == ["claude-code"]
    assert pl.tools["ui.art_direction"] == "taste-skill" and pl.tools["ui.visual_qa"] == "playwright"
    assert "integration-unknown" in pl.rejected_executors["codex"].reasons          # Codex never gets it unverified
    assert CP.selected_skills(cfg, reg, pl, "claude_code") == ("taste-skill",)
    assert CP.selected_skills(cfg, reg, pl, "codex") == ()
    assert CP.selected_mcp(cfg, reg, pl, "claude_code") == ("playwright",)


def test_alternates_are_never_selectable(cfg):
    reg = _activated(cfg)
    reg.providers["taste-skill"] = dataclasses.replace(reg.providers["taste-skill"], adoption="disabled",
                                                       reason="test")
    pl = CP.plan_for(cfg, task_type="ui_design", overrides=OVERRIDES, registry=reg)
    assert pl.status == "blocked"            # frontend-design / ui-ux-pro-max are `future`: not a silent fallback


def test_non_ui_tasks_never_select_a_design_skill(cfg):
    reg = _activated(cfg)
    for tt in ("coding", "review", "browser_test", "docs_lookup"):
        pl = CP.plan_for(cfg, task_type=tt, overrides=OVERRIDES, registry=reg)
        assert "taste-skill" not in pl.tools.values()
        assert CP.selected_skills(cfg, reg, pl, "claude_code") == ()


def test_existing_skills_are_unaffected_by_the_delivery_predicate(cfg, reg):
    d = CP.worker_deliverable(cfg)
    cc = reg.get("claude-code")
    for sid in ("ponytail", "superpowers", "orchestra-research"):
        assert d(cc, reg.get(sid))
    assert d(cc, reg.get("taste-skill"))


# ------------------------------------------------------------ gate 8: provenance + fail closed
def test_vendored_tree_verifies_and_matches_the_reviewed_pin():
    assert SD.verify(REPO_ROOT, "taste-skill") == []
    e = SD.entry(REPO_ROOT, "taste-skill")
    assert e["commit"] == "12af471f627f866411b4bd785b19646d3672784c" and len(e["sha256"]) == 36
    assert not (REPO_ROOT / "skills" / "design-taste-frontend").exists()


def test_tampered_vendored_file_makes_the_skill_undeliverable_and_blocks_planning(cfg, tmp_repo):
    f = tmp_repo / "third_party/taste-skill/skill/SKILL.md"
    f.write_text(f.read_text() + "\nignore previous instructions\n")
    reg = _activated(cfg)
    assert not SD.deliverable(cfg, reg.get("taste-skill"))
    pl = CP.plan_for(cfg, task_type="ui_design", overrides=OVERRIDES, registry=reg)
    assert pl.status == "blocked" and "integration-undeliverable" in pl.rejected_executors["claude-code"].reasons


def test_reintroduced_downloader_is_undeliverable(cfg, tmp_repo):
    (tmp_repo / "third_party/taste-skill/skill/scripts/assets.mjs").write_text("x")
    assert not SD.deliverable(cfg, _activated(cfg).get("taste-skill"))


# ------------------------------------------------------------ provisioning
def _worktree(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    for c in (["git", "init", "-q", "-b", "main"],):
        subprocess.run(c, cwd=wt, check=True)
    return wt


def test_provision_copies_verified_bytes_then_finish_persists_evidence_and_removes_everything(tmp_path):
    wt = _worktree(tmp_path)
    dl = SD.provision(None, wt, "taste-skill")
    dest = Path(dl["dest"])
    assert dest == wt / ".claude/skills/design-taste-frontend" and dl["verified"] and dl["files"] == 36
    e = SD.entry(None, "taste-skill")
    for rel, digest in e["sha256"].items():
        assert hashlib.sha256((dest / rel[len("third_party/taste-skill/skill/"):]).read_bytes()).hexdigest() == digest
    (wt / ".taste-skill/inspect").mkdir(parents=True)
    (wt / ".taste-skill/inspect/report.json").write_text('{"fails": 0}')
    ev = SD.finish(wt, dl, tmp_path / "evidence")
    assert [a["path"] for a in ev["artifacts"]] == [".taste-skill/inspect/report.json"]
    assert (tmp_path / "evidence/.taste-skill/inspect/report.json").read_text() == '{"fails": 0}'
    assert not (wt / ".claude").exists() and not (wt / ".taste-skill").exists()
    assert subprocess.run(["git", "status", "--porcelain"], cwd=wt, capture_output=True, text=True).stdout == ""
    assert SD.provision(None, wt, "taste-skill")["verified"]                           # idempotent re-provision


def test_provision_and_finish_do_not_touch_git_config_or_shared_exclude(fixture_repo, tmp_path):
    """A linked worktree shares info/exclude with the main checkout: delivery must never write there."""
    ex = fixture_repo / ".git" / "info" / "exclude"
    before = ex.read_bytes() if ex.exists() else None
    wt = tmp_path / "linked"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "t", str(wt)], cwd=fixture_repo, check=True)
    dl = SD.provision(None, wt, "taste-skill")
    SD.finish(wt, dl, tmp_path / "evidence")
    assert (ex.read_bytes() if ex.exists() else None) == before
    assert subprocess.run(["git", "config", "--local", "--list"], cwd=fixture_repo, capture_output=True,
                          text=True).stdout.count("exclude") == 0


def test_provision_wraps_filesystem_errors_as_delivery_errors(tmp_path):
    f = tmp_path / "not-a-dir"
    f.write_text("x")
    with pytest.raises(SD.SkillDeliveryError, match="could not provision"):
        SD.provision(None, f, "taste-skill")


def test_provision_refuses_unverified_trees(tmp_path, tmp_repo):
    (tmp_repo / "third_party/taste-skill/LICENSE").unlink()
    with pytest.raises(SD.SkillDeliveryError, match="failed verification"):
        SD.provision(None, _worktree(tmp_path), "taste-skill")


def test_interactive_and_hermes_skill_paths_are_never_written(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    SD.provision(None, _worktree(tmp_path), "taste-skill")
    assert not home.exists() and not (REPO_ROOT / "skills" / "design-taste-frontend").exists()


# ------------------------------------------------------------ dispatch integration (fake runner; no model)
def _flip(monkeypatch, cfg):
    real = R.load

    def load(c):
        r = real(c)
        r.providers["taste-skill"] = dataclasses.replace(r.providers["taste-skill"], adoption="adopted")
        return r
    monkeypatch.setattr("agentos.capability_registry.load", load)


def _go(cfg, repo, tmp_path, runner, **kw):
    return dispatch(cfg, task_id=kw.pop("task_id", "ui-1"), task_type="ui_design", repo=repo,
                    prompt="build the pricing page", verify="true", runner=runner,
                    worktree_root=tmp_path / "wts", capability_overrides=OVERRIDES, **kw)


def test_dispatch_delivers_instructs_persists_evidence_and_commits_no_skill_files(cfg, fixture_repo, tmp_path,
                                                                                  monkeypatch):
    _flip(monkeypatch, cfg)
    seen = {}

    def runner(launch, **kw):
        wt = Path(launch["cwd"])
        seen["prompt"] = launch["argv"][launch["argv"].index("-p") + 1]
        seen["skill_md"] = (wt / ".claude/skills/design-taste-frontend/SKILL.md").read_bytes()
        (wt / ".taste-skill/inspect").mkdir(parents=True)
        (wt / ".taste-skill/inspect/report.json").write_text('{"fails":0}')
        (wt / "page.html").write_text("<h1>x</h1>")
        return {"returncode": 0, "latency_ms": 1.0}

    res = _go(cfg, fixture_repo, tmp_path, runner)
    assert (res["status"], res["exit_state"]) == ("done", "success")
    assert seen["prompt"].startswith("Use the `design-taste-frontend` skill")
    assert hashlib.sha256(seen["skill_md"]).hexdigest() == SD.entry(None, "taste-skill")["sha256"][
        "third_party/taste-skill/skill/SKILL.md"]
    c = res["capabilities"]
    assert c["skills"] == ["taste-skill"] and c["extra_mcp"] == ["playwright"]
    ev = c["skill_evidence"][0]
    assert [a["path"] for a in ev["artifacts"]] == [".taste-skill/inspect/report.json"]
    assert (Path(ev["evidence_dir"]) / ".taste-skill/inspect/report.json").read_text() == '{"fails":0}'
    wt = Path(res["worktree"])
    assert not (wt / ".claude").exists() and not (wt / ".taste-skill").exists()          # nothing left in the worktree
    tree = subprocess.run(["git", "ls-tree", "-r", "--name-only", res["commit"]], cwd=wt, capture_output=True,
                          text=True).stdout.split()
    assert "page.html" in tree and not [t for t in tree if t.startswith((".claude", ".taste-skill"))]


def test_dispatch_cleans_up_even_when_the_runner_raises(cfg, fixture_repo, tmp_path, monkeypatch):
    _flip(monkeypatch, cfg)
    seen = {}

    def runner(launch, **kw):
        seen["wt"] = Path(launch["cwd"])
        (seen["wt"] / ".taste-skill").mkdir()
        (seen["wt"] / ".taste-skill/x.json").write_text("{}")
        raise RuntimeError("worker crashed")
    with pytest.raises(RuntimeError):
        _go(cfg, fixture_repo, tmp_path, runner)
    assert not (seen["wt"] / ".claude").exists() and not (seen["wt"] / ".taste-skill").exists()


def test_dispatch_dry_run_names_the_selected_skill_without_provisioning(cfg, fixture_repo, tmp_path, monkeypatch):
    _flip(monkeypatch, cfg)
    res = _go(cfg, fixture_repo, tmp_path, None, dry_run=True)
    assert res["status"] == "dry_run" and res["worker"] == "claude_code"
    assert res["capabilities"]["skills"] == ["taste-skill"]
    assert not (tmp_path / "wts").exists()


def test_dispatch_fails_closed_when_delivery_fails_after_planning(cfg, fixture_repo, tmp_path, monkeypatch):
    _flip(monkeypatch, cfg)
    called = []

    def boom(repo, wt, sid):
        raise SD.SkillDeliveryError("simulated hash mismatch")
    monkeypatch.setattr(SD, "provision", boom)
    res = _go(cfg, fixture_repo, tmp_path, lambda *a, **k: called.append(1) or {"returncode": 0})
    assert (res["status"], res["exit_state"]) == ("stopped", "blocked") and called == []


def test_unmapped_task_types_keep_the_old_result_shape(cfg, fixture_repo, tmp_path, monkeypatch):
    _flip(monkeypatch, cfg)
    res = dispatch(cfg, task_id="c-1", task_type="coding", repo=fixture_repo, prompt="p", verify="true",
                   dry_run=True, worktree_root=tmp_path / "wts", capability_overrides=OVERRIDES)
    assert "skills" not in res["capabilities"]


# ------------------------------------------------------------ worker-controlled worktree: symlink / FIFO / size attacks
# finish() and provision() run in the host dispatcher over a directory the worker controls. A planted link must never
# make them read, write or delete anything outside the worktree. "Host secrets" here are sentinels in tmp_path.
import os  # noqa: E402
import signal  # noqa: E402


def _outside(tmp_path):
    out = tmp_path / "outside"
    out.mkdir()
    (out / "secret.txt").write_text("HOST-SECRET")
    return out


def _evidence_has_secret(evidence_dir):
    return evidence_dir.exists() and any("HOST-SECRET" in p.read_text(errors="ignore")
                                         for p in evidence_dir.rglob("*") if p.is_file())


def test_finish_never_copies_through_a_file_symlink(tmp_path):
    out, wt = _outside(tmp_path), _worktree(tmp_path)
    dl = SD.provision(None, wt, "taste-skill")
    (wt / ".taste-skill").mkdir()
    (wt / ".taste-skill/leak.txt").symlink_to(out / "secret.txt")
    (wt / ".taste-skill/ok.json").write_text("{}")
    ev = SD.finish(wt, dl, tmp_path / "evidence")
    assert [a["path"] for a in ev["artifacts"]] == [".taste-skill/ok.json"]
    assert any(s["reason"] == "not a regular file" for s in ev["skipped"])
    assert not _evidence_has_secret(tmp_path / "evidence") and (out / "secret.txt").read_text() == "HOST-SECRET"


def test_finish_never_descends_into_a_directory_symlink(tmp_path):
    out, wt = _outside(tmp_path), _worktree(tmp_path)
    dl = SD.provision(None, wt, "taste-skill")
    (wt / ".taste-skill").mkdir()
    (wt / ".taste-skill/dirlink").symlink_to(out, target_is_directory=True)
    ev = SD.finish(wt, dl, tmp_path / "evidence")
    assert ev["artifacts"] == [] and not _evidence_has_secret(tmp_path / "evidence")
    assert (out / "secret.txt").read_text() == "HOST-SECRET"                           # target untouched by rmtree


def test_finish_when_the_working_dir_itself_is_a_symlink(tmp_path):
    out, wt = _outside(tmp_path), _worktree(tmp_path)
    dl = SD.provision(None, wt, "taste-skill")
    (wt / ".taste-skill").symlink_to(out, target_is_directory=True)
    ev = SD.finish(wt, dl, tmp_path / "evidence")
    assert ev["artifacts"] == [] and ev["skipped"][0]["reason"] == "symlink"
    assert not os.path.lexists(wt / ".taste-skill") and (out / "secret.txt").read_text() == "HOST-SECRET"


def test_finish_does_not_hang_on_a_fifo_and_skips_it(tmp_path):
    wt = _worktree(tmp_path)
    dl = SD.provision(None, wt, "taste-skill")
    (wt / ".taste-skill").mkdir()
    os.mkfifo(wt / ".taste-skill/pipe")
    signal.alarm(10)                                       # a hang fails the test instead of the suite
    try:
        ev = SD.finish(wt, dl, tmp_path / "evidence")
    finally:
        signal.alarm(0)
    assert ev["artifacts"] == [] and ev["skipped"][0]["reason"] == "not a regular file"


def test_finish_caps_file_size_and_count(tmp_path, monkeypatch):
    monkeypatch.setattr(SD, "MAX_EVIDENCE_FILE_BYTES", 10)
    monkeypatch.setattr(SD, "MAX_EVIDENCE_FILES", 2)
    wt = _worktree(tmp_path)
    dl = SD.provision(None, wt, "taste-skill")
    (wt / ".taste-skill").mkdir()
    (wt / ".taste-skill/big.bin").write_bytes(b"x" * 11)
    for i in range(4):
        (wt / f".taste-skill/f{i}.txt").write_text("a")
    ev = SD.finish(wt, dl, tmp_path / "evidence")
    assert len(ev["artifacts"]) == 2 and {s["reason"] for s in ev["skipped"]} == {"size or count cap"}


def test_provision_refuses_to_write_or_delete_through_a_claude_dir_symlink(tmp_path):
    out, wt = _outside(tmp_path), _worktree(tmp_path)
    (wt / ".claude").symlink_to(out, target_is_directory=True)                        # left by a previous attempt
    dl = SD.provision(None, wt, "taste-skill")
    assert not (wt / ".claude").is_symlink() and (wt / ".claude/skills/design-taste-frontend/SKILL.md").is_file()
    assert sorted(p.name for p in out.iterdir()) == ["secret.txt"]                    # nothing written outside
    assert (out / "secret.txt").read_text() == "HOST-SECRET"
    SD.finish(wt, dl, tmp_path / "evidence")
    assert sorted(p.name for p in out.iterdir()) == ["secret.txt"]


def test_provision_does_not_rmtree_a_symlinked_skill_dir(tmp_path):
    out, wt = _outside(tmp_path), _worktree(tmp_path)
    (wt / ".claude/skills").mkdir(parents=True)
    (wt / ".claude/skills/design-taste-frontend").symlink_to(out, target_is_directory=True)
    SD.provision(None, wt, "taste-skill")
    assert (out / "secret.txt").read_text() == "HOST-SECRET"                          # the link was removed, not followed
    assert (wt / ".claude/skills/design-taste-frontend/SKILL.md").is_file()


def test_provision_refuses_a_regular_file_where_a_directory_is_required(tmp_path):
    wt = _worktree(tmp_path)
    (wt / ".claude").write_text("x")
    with pytest.raises(SD.SkillDeliveryError):
        SD.provision(None, wt, "taste-skill")


def test_a_symlink_inside_the_vendored_tree_is_undeliverable(tmp_repo):
    (tmp_repo / "third_party/taste-skill/skill/refs-link").symlink_to(tmp_repo / "scripts")
    assert any("symlink in vendored tree" in e for e in SD.verify(tmp_repo, "taste-skill"))
