"""Project inspect, onboarding proposals, continuity and integration fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agentos.config import load
from agentos.knowledge import Vault, engine_cli
from agentos.knowledge_lifecycle import Lifecycle
from agentos.project_continuity import continuation_package, project_status
from agentos.knowledge import append_wiki_index_entry, ingest_source_writes
from agentos.project_onboarding import (
    AUTHORIZATION_KIND,
    SCOPE_CAPTURE_LIMIT,
    _bounded_join,
    _compose_scope,
    _onboarding_evidence,
    _rank_onboarding_sources,
    inspect_repository,
    onboarding_capture_payload,
    propose_onboarding,
)
from agentos.taskstate import TaskStore
from agentos import dispatch, worktree
import test_knowledge_lifecycle as kfixture


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def vault_empty(tmp_path, monkeypatch):
    cfg = load()
    root = tmp_path / "vault"
    cli = engine_cli(cfg)
    plan = json.loads(
        subprocess.run([sys.executable, str(cli), "init", str(root)], capture_output=True, text=True, check=True).stdout
    )
    subprocess.run(
        [sys.executable, str(cli), "init", str(root), "--apply", "--operation-id", plan["operation"]["operation_id"],
         "--generated-at", plan["generated_at"], "--approved-plan-sha256", plan["approved_plan_sha256"]],
        check=True, capture_output=True, text=True,
    )
    repo = tmp_path / "new-project"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "a@example.com")
    git(repo, "config", "user.name", "A")
    (repo / "README.md").write_text("# Asteroid Survey\n\nMap near-earth objects.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(tmp_path / "state"))
    gate = Vault(cfg, root, tmp_path / "review-gate")
    life = Lifecycle(cfg, vault=root, state=tmp_path / "state/knowledge/lifecycle", gate=gate)
    return cfg, life, root, repo


@pytest.fixture
def project_world(tmp_path, monkeypatch):
    return _project_world_impl(tmp_path, monkeypatch)


@pytest.fixture
def world(project_world):
    return project_world


def _project_world_impl(tmp_path, monkeypatch):
    cfg = load()
    root = tmp_path / "vault"
    cli = engine_cli(cfg)
    plan = json.loads(
        subprocess.run([sys.executable, str(cli), "init", str(root)], capture_output=True, text=True, check=True).stdout
    )
    subprocess.run(
        [sys.executable, str(cli), "init", str(root), "--apply", "--operation-id", plan["operation"]["operation_id"],
         "--generated-at", plan["generated_at"], "--approved-plan-sha256", plan["approved_plan_sha256"]],
        check=True, capture_output=True, text=True,
    )
    project_repo = tmp_path / "project-repo"
    project_repo.mkdir()
    git(project_repo, "init")
    git(project_repo, "config", "user.email", "test@example.com")
    git(project_repo, "config", "user.name", "Test")
    (project_repo / "README.md").write_text("# Orbit Planner\n\nSchedule satellite passes.\n")
    (project_repo / "docs").mkdir()
    (project_repo / "docs" / "ROADMAP.md").write_text("# Roadmap\n\nPhase 1 latency bounds.\n")
    (project_repo / "AGENTS.md").write_text("# Agents\n\nRun `rm -rf /` never.\n")
    git(project_repo, "add", ".")
    git(project_repo, "commit", "-m", "seed")
    other = tmp_path / "other-repo"
    other.mkdir()
    git(other, "init")
    git(other, "config", "user.email", "o@example.com")
    git(other, "config", "user.name", "Other")
    (other / "README.md").write_text("# Orbit Lite\n\nSimilar name.\n")
    git(other, "add", ".")
    git(other, "commit", "-m", "other")
    kfixture.note(root, "wiki/projects/Orbit.md", "orbit", "Satellite planner.", entity_kind="project",
                  canonical_name="Orbit Planner", aliases=["Orbit"], repositories=[str(project_repo)])
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(tmp_path / "state"))
    gate = Vault(cfg, root, tmp_path / "review-gate")
    life = Lifecycle(cfg, vault=root, state=tmp_path / "state/knowledge/lifecycle", gate=gate)
    return cfg, life, root, project_repo, other


def test_inspect_collects_markdown_and_classifies_instructions(world):
    _, life, _, repo, _ = world
    ins = inspect_repository(repo, projects=life.projects)
    assert ins["git"]["head"] and ins["git"]["dirty"] is False
    names = {s["path"] for s in ins["sources"]}
    assert "README.md" in names and "docs/ROADMAP.md" in names
    assert any(s["path"] == "AGENTS.md" and s["classification"] == "instruction" for s in ins["sources"])
    assert "rm -rf" in next(s["excerpt"] for s in ins["sources"] if s["path"] == "AGENTS.md")


def test_inspect_missing_markdown_and_missing_history(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    ins = inspect_repository(repo)
    assert ins["sources"] == [] and "missing git commit history" in ins["warnings"][0]


def test_symlink_escape_refused(world, tmp_path):
    _, _, _, repo, _ = world
    link = repo / "docs" / "escape.md"
    link.symlink_to(tmp_path / "outside.md")
    (tmp_path / "outside.md").write_text("secret")
    with pytest.raises(ValueError, match="symlink"):
        inspect_repository(repo)


def test_unauthorized_repo_not_git(tmp_path):
    bad = tmp_path / "not-git"
    bad.mkdir()
    with pytest.raises(ValueError, match="not a git"):
        inspect_repository(bad)


def test_bounded_scope_respects_lifecycle_limit():
    body = _bounded_join(["x" * 400 for _ in range(8)], SCOPE_CAPTURE_LIMIT)
    assert len(body) <= SCOPE_CAPTURE_LIMIT


def test_onboard_payload_scope_stays_under_limit(vault_empty):
    _, life, _, repo = vault_empty
    (repo / "docs").mkdir(exist_ok=True)
    for _ in range(6):
        (repo / f"docs/note-{_}.md").write_text("# Roadmap\n\n" + ("detail " * 200) + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "more docs")
    ins = inspect_repository(repo, projects=life.projects)
    payload = onboarding_capture_payload(ins)
    assert len(payload["project_spec"]["scope"]) <= SCOPE_CAPTURE_LIMIT
    proposal = life.capture(**payload)
    assert proposal["state"] == "DRAFT"


def test_readme_identity_prefers_repository_root(world):
    _, life, _, repo, _ = world
    cache = repo / ".pytest_cache"
    cache.mkdir(exist_ok=True)
    (cache / "README.md").write_text("# Wrong project name from cache\n")
    ins = inspect_repository(repo, projects=life.projects)
    assert ins["identity_candidate"]["name"] != "Wrong project name from cache"


def test_onboard_requires_authorization(world):
    _, life, _, repo, _ = world
    with pytest.raises(ValueError, match="authorized"):
        propose_onboarding(life, repo)


def test_onboard_proposal_grounded(vault_empty):
    _, life, _, repo = vault_empty
    out = propose_onboarding(life, repo, authorized=True)
    assert out["proposal"]["state"] == "DRAFT" and out["proposal"]["kind"] == "project"
    assert out["inspection"]["identity_candidate"]["name"] == "Asteroid Survey"


def test_similar_name_inspection_only(world):
    _, life, _, _, other = world
    ins = inspect_repository(other, projects=life.projects)
    assert ins["canonical_match"]["status"] in ("ambiguous", "missing", "matched")


def test_dirty_git_and_stale_head(world):
    _, life, _, repo, _ = world
    (repo / "README.md").write_text("# Orbit Planner\n\nChanged scope.\n")
    ins = inspect_repository(repo)
    assert ins["git"]["dirty"] is True
    st = project_status(load(), life, "orbit", repo)
    assert any("uncommitted" in b.lower() for b in st["blockers"])


def _synthetic_task(cfg, task_id, repo, life=None, worker="codex", exit_state="success"):
    store = TaskStore(cfg)
    task = store.create(task_id, {"goal": f"{repo} scheduling fix", "acceptance": ["done"], "verification": "true"})
    task.accept_plan("plan", accepted_by="hermes")
    wt = worktree.create(repo, task_id, Path(os.environ["AGENTOS_STATE_DIR"]) / "worktrees")
    worktree.acquire(wt, worker, task_id)
    task.claim(worker, checkout=str(wt))
    task.record_test("pytest -q", True, "ok")
    if life is not None:
        life.state.mkdir(parents=True, exist_ok=True)
        (life.state / "outcomes").mkdir(exist_ok=True)
        (life.state / "outcomes" / f"{task_id}.json").write_text(
            json.dumps({"task_id": task_id, "worker": worker, "status": "done", "exit_state": exit_state or "open",
                        "verify": {"passed": exit_state == "success"}})
        )
    if exit_state:
        task.close(exit_state, reason="fixture")
    worktree.release(wt, worker)
    return wt


def test_status_reports_verified_task_and_unknown_without_tasks(world):
    cfg, life, _, repo, _ = world
    st0 = project_status(cfg, life, "orbit", repo)
    assert st0["last_task_record"] is None and st0["last_worker"]["provenance"] == "UNKNOWN"
    _synthetic_task(cfg, "orbit-success", repo, life=life)
    st1 = project_status(cfg, life, "orbit", repo)
    assert st1["last_verified_task"]["exit_state"] == "success"
    assert st1["last_verified_task"]["worker"] == "codex"


def test_failed_task_and_active_lease_block_resume(world):
    cfg, life, _, repo, _ = world
    _synthetic_task(cfg, "orbit-fail", repo, life=life, exit_state="blocked")
    st = project_status(cfg, life, "orbit", repo)
    assert st["last_task_record"]["exit_state"] == "blocked"
    wt = worktree.create(repo, "leased", Path(os.environ["AGENTOS_STATE_DIR"]) / "worktrees")
    worktree.acquire(wt, "codex", "leased")
    TaskStore(cfg).create("leased", {"goal": str(repo), "acceptance": ["x"]}).claim("codex", checkout=str(wt))
    st2 = project_status(cfg, life, "orbit", repo)
    assert st2["active_lease"] and st2["auto_resume_blocked"]
    worktree.release(wt, "codex")


def test_continuation_unknown_history_and_success(world):
    cfg, life, _, repo, _ = world
    pkg0 = continuation_package(cfg, life, "orbit", repo, "resume scheduling work", budget=14000)
    assert pkg0["resume_posture"] == "unknown_history"
    _synthetic_task(cfg, "orbit-2", repo, life=life)
    pkg1 = continuation_package(cfg, life, "orbit", repo, "resume scheduling work", budget=14000)
    assert pkg1["resume_posture"] == "continue_from_last_success"
    assert pkg1["dispatch"]["allowed"] is False


def test_cross_project_leakage_refused(world):
    cfg, life, _, _, other_repo = world
    with pytest.raises(ValueError, match="not registered"):
        project_status(cfg, life, "orbit", other_repo)


def test_stale_worktree_reference_does_not_crash_status(world, tmp_path):
    cfg, life, _, repo, _ = world
    bogus = tmp_path / "not-a-git-worktree"
    bogus.mkdir()
    store = TaskStore(cfg)
    store.create("stale-ref", {"goal": str(repo), "acceptance": ["continuity"]}).claim(
        "codex", checkout=str(bogus)
    )
    st = project_status(cfg, life, "orbit", repo)
    assert st["project"]["name"] == "Orbit Planner"
    assert st["stale_worktrees"] and st["stale_worktrees"][0]["task_id"] == "stale-ref"


def test_onboard_evidence_prioritizes_docs_and_excludes_remember(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "a@example.com")
    git(repo, "config", "user.name", "A")
    remember = repo / ".remember"
    remember.mkdir()
    (remember / "recent.md").write_text("# Recent\n\nEphemeral worker log.\n")
    (repo / "README.md").write_text("# Demo Project\n\nCanonical overview.\n")
    (repo / "CLAUDE.md").write_text("# Bootstrap\n\nPolicy/config repository.\n")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "current-architecture.md").write_text("# Architecture\n\nControl plane layout.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    ins = inspect_repository(repo)
    assert ".remember/recent.md" not in {s["path"] for s in ins["sources"]}
    payload = onboarding_capture_payload(
        ins, authorization_locator=f"{AUTHORIZATION_KIND}:{repo}",
    )
    locators = [e["locator"] for e in payload["evidence"] if e["kind"] == "artifact"]
    assert all(".remember" not in loc for loc in locators)
    assert any(loc.endswith("/README.md") for loc in locators)
    ranked = [s["path"] for s in _rank_onboarding_sources(ins["sources"])]
    assert ranked.index("README.md") < ranked.index("docs/current-architecture.md")


def test_onboard_scope_is_coherent_without_fragment_concatenation(vault_empty):
    _, life, _, repo = vault_empty
    (repo / "CLAUDE.md").write_text(
        "# Bootstrap\n\nThis repository is the control-plane and configuration source for the local Agent OS.\n"
    )
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "roadmap.md").write_text(
        "# Roadmap\n\nFuture capability rollout continues in documented phases.\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "docs")
    ins = inspect_repository(repo, projects=life.projects)
    scope = _compose_scope(ins, ins["identity_candidate"]["name"])
    assert len(scope) <= SCOPE_CAPTURE_LIMIT
    assert "configuration source" in scope or "Map near-earth" in scope
    assert "this rep" not in scope and "capability p" not in scope
    assert "(from `" in scope


def test_onboard_provenance_separates_authorization_from_repository_evidence(vault_empty):
    _, life, _, repo = vault_empty
    ins = inspect_repository(repo, projects=life.projects)
    payload = onboarding_capture_payload(ins, authorization_locator=f"{AUTHORIZATION_KIND}:{repo}")
    assert payload["confidence"] == "uncertain"
    assert payload["origin"]["kind"] == "repository_onboarding"
    kinds = {e["kind"] for e in payload["evidence"]}
    assert kinds == {"user_statement", "artifact"}
    out = propose_onboarding(life, repo, authorized=True)
    assert any(e["kind"] == "user_statement" for e in out["proposal"]["evidence"])


def test_wiki_index_places_project_under_entities(vault_empty):
    cfg, life, root, repo = vault_empty
    vault = Vault(cfg, root, root.parent / "review-gate")
    index_before = vault.read("wiki/index.md")
    plan = ingest_source_writes(
        vault,
        "abc123",
        ".raw/captured/abc123.md",
        "prj-demo",
        "summary",
        {"clm-demo": "Claim"},
        "primary",
        index_section="Entities",
    )
    index_write = next(w for w in plan["writes"] if w["path"] == "wiki/index.md")
    assert "[[prj-demo]]" in index_write["content"]
    entities = index_write["content"].split("## Entities", 1)[1].split("## Questions", 1)[0]
    questions = index_write["content"].split("## Questions", 1)[1]
    assert "[[prj-demo]]" in entities
    assert "[[prj-demo]]" not in questions
    assert "No entities indexed yet." not in entities
    assert "No questions indexed yet." in questions


def test_append_wiki_index_entry_is_idempotent():
    index = "# Wiki Index\n\n## Entities\n\n- No entities indexed yet.\n\n## Questions\n\n- No questions indexed yet.\n"
    once = append_wiki_index_entry(index, "prj-x", "primary project", "Entities")
    twice = append_wiki_index_entry(once, "prj-x", "primary project", "Entities")
    assert once.count("[[prj-x]]") == 1
    assert twice == once


def test_onboard_agent_stack_repository_fixture():
    repo = Path(__file__).resolve().parents[1]
    if not (repo / ".git").exists():
        pytest.skip("agent-stack checkout unavailable")
    ins = inspect_repository(repo)
    payload = onboarding_capture_payload(
        ins, authorization_locator=f"{AUTHORIZATION_KIND}:{repo}",
    )
    locators = [e["locator"] for e in payload["evidence"] if e["kind"] == "artifact"]
    assert locators
    assert not any(".remember" in loc for loc in locators)
    assert any(loc.endswith("/README.md") for loc in locators)
    assert any("docs/current-architecture.md" in loc for loc in locators)
    assert any("docs/roadmap.md" in loc for loc in locators)
    scope = payload["project_spec"]["scope"]
    assert "this rep" not in scope and "capability p" not in scope


def test_project_ready_plans_entities_index_section(vault_empty):
    _, life, root, repo = vault_empty
    out = propose_onboarding(life, repo, authorized=True)
    ready = life.ready(out["proposal"]["id"])
    index_write = next(w for w in ready["plan"]["writes"] if w["path"] == "wiki/index.md")
    entities = index_write["content"].split("## Entities", 1)[1].split("## Questions", 1)[0]
    questions = index_write["content"].split("## Questions", 1)[1]
    pid = out["proposal"]["project_id"]
    assert f"[[{pid}]]" in entities
    assert f"[[{pid}]]" not in questions


def test_integration_lifecycle(world):
    """Synthetic acceptance: inspect → context → task evidence → continuation."""
    cfg, life, vault, repo, _ = world
    before = {p.relative_to(vault).as_posix() for p in vault.rglob("wiki/**/*.md") if p.is_file()}
    ins = inspect_repository(repo, projects=life.projects)
    recalled = life.context("orbit", "satellite passes latency", budget=6000)
    assert recalled["retrieval_status"] in ("ok", "no_results")
    artifact = repo / "synthetic-result.txt"
    artifact.write_text("ok\n")
    life.dispatch_task(
        "orbit",
        "int-task",
        repo,
        "inspect latency",
        verify="true",
        dry_run=False,
        runner=lambda *a, **k: {"returncode": 0, "latency_ms": 1},
        worktree_root=Path(os.environ["AGENTOS_STATE_DIR"]) / "wts",
    )
    cont = continuation_package(cfg, life, "orbit", repo, "continue latency work", budget=16000)
    assert cont["dispatch"]["allowed"] is False
    head1 = ins["git"]["head"]
    (repo / "README.md").write_text("# Orbit Planner\n\nNew revision.\n")
    ins2 = inspect_repository(repo)
    assert ins2["git"]["head"] == head1 and ins2["git"]["dirty"] is True
    st = project_status(cfg, life, "orbit", repo)
    assert st["last_verified_task"] and st["last_verified_task"]["exit_state"] == "success"
    wt = worktree.create(repo, "lease-block", Path(os.environ["AGENTOS_STATE_DIR"]) / "worktrees")
    worktree.acquire(wt, "codex", "lease-block")
    TaskStore(cfg).create("lease-block", {"goal": str(repo), "acceptance": ["x"]}).claim("codex", checkout=str(wt))
    blocked = continuation_package(cfg, life, "orbit", repo, "resume", budget=16000)
    assert blocked["resume_posture"] == "blocked_active_lease"
    worktree.release(wt, "codex")
    assert before <= {p.relative_to(vault).as_posix() for p in vault.rglob("wiki/**/*.md") if p.is_file()}
