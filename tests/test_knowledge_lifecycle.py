"""Lifecycle contracts; all mutations target disposable vaults, never SecondBrain.

The reviewer helper is deliberately test-only: production exposes no approval or
canonical-apply command. These tests use the real claude-obsidian transaction gate.
"""
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agentos.config import load
from agentos.knowledge import Vault, engine_cli


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def ground_fixture_note(root, rel):
    """Seed independently verified synthetic provenance, not production approval logic."""
    from agentos.knowledge import stable_source_id
    path=root/rel;raw=b'Synthetic independent operator verification: polar coverage.\n'
    checksum=hashlib.sha256(raw).hexdigest();locator=f'.raw/captured/{checksum}.md'
    evidence=root/locator;evidence.parent.mkdir(parents=True,exist_ok=True);evidence.write_bytes(raw)
    sid=stable_source_id('file',locator,checksum)
    text=path.read_text().replace('---\n',f'---\nsource_id: {sid}\nsha256: {checksum}\n',1);path.write_text(text)
    ledger=root/'wiki/meta/ledgers/source-ledger.json';data=json.loads(ledger.read_text())
    data['sources'][sid]={'origin':{'kind':'file','locator':locator},'content_sha256':checksum,
                          'authority':'primary','review_status':'reviewed','pages':[rel]}
    ledger.write_text(json.dumps(data))


def note(root, path, project, body, **extra):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = dict(type="concept", title=p.stem, status="seed", created="2026-11-13",
              updated="2026-11-13", tags=["test"], project_id=project, **extra)
    p.write_text("---\n" + yaml.safe_dump(fm) + "---\n\n" + body + "\n")
    index = root / "wiki/index.md"
    if index.exists():
        index.write_text(index.read_text() + f"\n- [[{p.stem}]]\n")
    return p


@pytest.fixture
def world(tmp_path, monkeypatch):
    from agentos.knowledge_lifecycle import Lifecycle
    cfg = load()
    root = tmp_path / "vault"
    cli = engine_cli(cfg)
    def engine(*args):
        r = subprocess.run([sys.executable, str(cli), *args], capture_output=True, text=True,
                           cwd=tmp_path, check=True)
        return json.loads(r.stdout)
    plan = engine("init", str(root))
    engine("init", str(root), "--apply", "--operation-id", plan["operation"]["operation_id"],
           "--generated-at", plan["generated_at"], "--approved-plan-sha256", plan["approved_plan_sha256"])
    repo = tmp_path / "repo"
    repo.mkdir()
    note(root, "wiki/projects/Orbit.md", "orbit", "Satellite planner.", entity_kind="project",
         canonical_name="Orbit Planner", aliases=["Orbit", "Shared"], scope="Satellite scheduling",
         repositories=[str(repo)], open_questions=["Ground station latency?"])
    note(root, "wiki/projects/Other.md", "other", "Unrelated project.", entity_kind="project",
         canonical_name="Other Project", aliases=["Shared"])
    monkeypatch.setenv("AGENTOS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENTOS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    monkeypatch.setenv("AGENTOS_RESOURCE_STATE", str(tmp_path / "resources.json"))
    gate = Vault(cfg, root, tmp_path / "review-gate")
    life = Lifecycle(cfg, vault=root, state=tmp_path / "state/knowledge/lifecycle", gate=gate)
    return life, root, repo, engine


def capture(life, **kw):
    values = dict(project="orbit", kind="idea", summary="Try orbital scheduling with bounded latency.",
                  evidence=[{"kind": "user_statement", "locator": "session:synthetic-user-1"}],
                  authorized=True)
    values.update(kw)
    return life.capture(**values)


def reviewer_stage(life, pid):
    """Explicit test-only reviewer handoff; never callable through production CLI."""
    p = life.show(pid)
    plan = p["plan"]
    for rel, expected in plan["expected_hashes"].items():
        if life.gate.sha(rel) != expected:
            raise ValueError("stale reviewer handoff")
    inbox = life.gate.root / "inbox" / (pid + ".md")
    inbox.write_text(plan["payload"])
    life.gate.capture([str(inbox.relative_to(life.gate.root))])
    return life.gate.propose(pid, "ingest", plan["writes"], p["origin"]["actor"],
                             plan["source_manifest_updates"], plan["address_requests"])


def reviewer_approve(life, pid):
    meta = reviewer_stage(life, pid)
    life.gate.approve(pid, "independent-test-human", meta["approval_sha256"],
                      "human:test-only-explicit-approval")
    return life.reconcile(pid)


def test_project_exact_alias_ambiguity_and_missing(world):
    life, *_ = world
    assert life.projects.resolve("Orbit")["project"]["id"] == "orbit"
    assert life.projects.resolve("Shared")["status"] == "ambiguous"
    assert life.projects.resolve("orbital keyword")["status"] == "missing"
    assert life.projects.resolve("unknown")["status"] == "missing"


def test_capture_requires_authorization_and_provenance(world):
    life, root, *_ = world
    for kw in [dict(authorized=False), dict(evidence=[]), dict(project="Shared"), dict(project="missing")]:
        with pytest.raises(ValueError):
            capture(life, **kw)
    assert not list((root / "inbox").glob("kp-*.md"))


@pytest.mark.parametrize("summary", ["api_key=super-secret-value", "Bearer abcdefghijklmnop",
                                    "Contact personal@example.com", "-----BEGIN PRIVATE KEY-----"])
def test_sensitive_capture_is_refused_without_persistence(world, summary):
    life, *_ = world
    with pytest.raises(ValueError, match="sensitive"):
        capture(life, summary=summary)
    assert life.list() == []


def test_capture_idempotent_concurrent_and_restart_recovery(world):
    life, *_ = world
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda _: capture(life)["id"], range(8)))
    assert len(set(ids)) == 1 and len(life.list()) == 1
    from agentos.knowledge_lifecycle import Lifecycle
    restored = Lifecycle(life.cfg, vault=life.root, state=life.state, gate=life.gate)
    assert restored.show(ids[0])["state"] == "DRAFT"


def test_idea_review_commit_and_subsequent_real_bm25_recall(world):
    life, root, *_ = world
    p = capture(life)
    ready = life.ready(p["id"])
    assert ready["state"] == "READY_FOR_REVIEW" and "+" in ready["diff"]
    assert not (root / ready["target"]).exists()
    reviewer_approve(life, p["id"])
    assert life.show(p["id"])["state"] == "APPROVED"
    result = life.gate.apply(p["id"])
    assert result["lint"]["issues_found"] == 0
    done = life.reconcile(p["id"])
    assert done["state"] == "COMMITTED" and done["receipt"]["approval_ref"].startswith("human:")
    context = life.context("orbit", "orbital scheduling bounded latency", budget=6000)
    assert ready["target"] in [s["path"] for s in context["sources"]]
    assert life.reconcile(p["id"])["receipt"] == done["receipt"]


def test_reject_and_illegal_transitions_never_write_wiki(world):
    life, root, *_ = world
    p = capture(life)
    ready = life.ready(p["id"])
    life.reject(p["id"], "Not pursuing this idea")
    with pytest.raises(ValueError):
        life.ready(p["id"])
    with pytest.raises(ValueError):
        life.reconcile(p["id"])
    assert not (root / ready["target"]).exists()


def test_stale_handoff_rejects_concurrent_edit(world):
    life, root, *_ = world
    p = capture(life)
    life.ready(p["id"])
    log = root / "wiki/log.md"
    log.write_text(log.read_text() + "\nHuman concurrent change\n")
    with pytest.raises(ValueError, match="stale"):
        reviewer_stage(life, p["id"])
    assert "Human concurrent change" in log.read_text()


def test_two_approved_proposals_cannot_overwrite_each_other(world):
    life, root, *_ = world
    a = capture(life)
    b = capture(life, summary="Try a second independent orbit experiment.")
    life.ready(a["id"]); life.ready(b["id"])
    reviewer_approve(life, a["id"])
    life.gate.apply(a["id"])
    with pytest.raises(ValueError, match="stale"):
        reviewer_stage(life, b["id"])
    assert life.reconcile(a["id"])["state"] == "COMMITTED"


def test_interrupted_lifecycle_finalization_recovers_from_engine_journal(world):
    life, *_ = world
    p = capture(life); life.ready(p["id"]); reviewer_approve(life, p["id"])
    life.gate.apply(p["id"])  # Simulate exit before the lifecycle receipt was persisted.
    from agentos.knowledge_lifecycle import Lifecycle
    restarted = Lifecycle(life.cfg, vault=life.root, state=life.state, gate=life.gate)
    assert restarted.reconcile(p["id"])["state"] == "COMMITTED"


def test_forged_or_self_approval_is_not_accepted(world):
    life, *_ = world
    p = capture(life); life.ready(p["id"])
    assert life.reconcile(p["id"])["state"] == "READY_FOR_REVIEW"
    meta = reviewer_stage(life, p["id"])
    life.gate.approval_dir.mkdir(parents=True, exist_ok=True)
    approval = {"operation_id":p["id"], "reviewer":p["origin"]["actor"],
                "proposer":p["origin"]["actor"], "human_approval_ref":"human:forged",
                "approval_sha256":meta["approval_sha256"]}
    (life.gate.approval_dir / ("knowledge-"+p["id"]+".json")).write_text(json.dumps(approval))
    with pytest.raises(ValueError, match="independent"):
        life.reconcile(p["id"])


def test_scoped_context_no_results_and_no_cross_project_leak(world):
    life, root, *_ = world
    note(root, "wiki/decisions/Orbit Decision.md", "orbit", "Choose polar coverage for orbit missions.",
         record_kind="decision", authority="primary", review_state="reviewed", evidence_status="verified")
    ground_fixture_note(root,"wiki/decisions/Orbit Decision.md")
    note(root, "wiki/decisions/Other Secret.md", "other", "Polar coverage other-project confidential marker.")
    before = {str(p):digest(p) for p in root.rglob('*') if p.is_file()}
    c = life.context("orbit", "polar coverage", budget=4500)
    text = json.dumps(c)
    assert "Orbit Decision" in text and "Other Secret" not in text
    assert "other-project confidential marker" not in text
    assert c["prior_decisions"] and c["verified_facts"]
    assert len(json.dumps(c, ensure_ascii=False)) <= 4500
    assert all(s["sha256"] for s in c["sources"])
    assert before == {str(p):digest(p) for p in root.rglob('*') if p.is_file()}
    assert life.context("orbit", "quantum banana zebra", budget=4500)["retrieval_status"] == "no_results"


def test_context_budget_secrets_and_invalid_worker_profile_fail_closed(world):
    life, root, *_ = world
    note(root, "wiki/concepts/Sensitive.md", "orbit", "orbit api_key=do-not-export-this-value")
    c = life.context("orbit", "orbit", budget=4000)
    assert "do-not-export-this-value" not in json.dumps(c)
    with pytest.raises(ValueError):life.context("orbit", "orbit", budget=100)
    with pytest.raises(Exception):life.context("orbit", "orbit", worker="opencode")


def test_update_preserves_metadata_links_and_checks_project_and_source_versions(world):
    life, root, *_ = world
    target = note(root, "wiki/concepts/Existing.md", "orbit", "Keep [[Orbit]] and prior content.")
    p = capture(life, operation="update", target="wiki/concepts/Existing.md")
    ready = life.ready(p["id"])
    replacement = next(x['content'] for x in ready['plan']['writes'] if x['path']==p['target'])
    assert target.read_text() in replacement
    reviewer_approve(life,p['id']);life.gate.apply(p['id']);life.reconcile(p['id'])
    assert "Keep [[Orbit]] and prior content." in target.read_text()
    foreign = note(root,"wiki/concepts/Foreign.md","other","Not authorized for orbit.")
    with pytest.raises(ValueError):capture(life,operation="update",target=str(foreign.relative_to(root)))


@pytest.mark.parametrize("target", ["wiki/../outside.md", "wiki/.vault-meta/x.md", "/tmp/x.md", "wiki/log.md"])
def test_target_allowlist_blocks_path_escape_and_infrastructure(world,target):
    life,*_=world
    with pytest.raises(ValueError):capture(life,operation="update",target=target)


def test_broken_links_and_symlink_escape_are_rejected(world,tmp_path):
    life,root,*_=world
    with pytest.raises(ValueError):capture(life,related=["wiki/concepts/Missing.md"])
    (root/'wiki/concepts').mkdir(exist_ok=True)
    (root/'wiki/concepts/Escape.md').symlink_to(tmp_path/'outside.md')
    with pytest.raises(ValueError):capture(life,operation="update",target="wiki/concepts/Escape.md")


def test_changed_project_and_artifact_hash_refuse_ready(world):
    life,root,repo,*_=world
    artifact=repo/'result.txt';artifact.write_text('3 passed')
    p=capture(life,evidence=[{'kind':'artifact','locator':str(artifact),'sha256':digest(artifact)}])
    artifact.write_text('0 passed')
    with pytest.raises(ValueError,match="stale|hash"):life.ready(p['id'])
    q=capture(life,summary="A distinct idea")
    project=root/'wiki/projects/Orbit.md';project.write_text(project.read_text()+'\nNew project scope\n')
    with pytest.raises(ValueError,match="stale"):life.ready(q['id'])


def test_worker_success_failure_partial_and_idempotency(world):
    life,root,repo,*_=world
    artifact=repo/'verified.txt';artifact.write_text('3 tests passed')
    evidence=[{'kind':'artifact','locator':str(artifact),'sha256':digest(artifact)}]
    for status,exit_state in [('retryable',None),('stopped','blocked')]:
        r=life.ingest_result('orbit',{'task_id':'failed-1','status':status,'exit_state':exit_state},
                             summary='No validated success',evidence=evidence,authorized=True)
        assert r['proposal'] is None and r['status'] in ['partial','failure']
    result={'task_id':'success-1','status':'done','exit_state':'success','worker':'codex',
            'verify':{'passed':True}}
    r=life.ingest_result('orbit',result,summary='Bounded scheduler passed its checks.',evidence=evidence,authorized=True)
    again=life.ingest_result('orbit',result,summary='Bounded scheduler passed its checks.',evidence=evidence,authorized=True)
    assert r['proposal']['id']==again['proposal']['id']
    assert r['proposal']['confidence']=='worker_report'
    assert not (root/r['proposal']['target']).exists()


def test_prepare_dispatch_uses_existing_router_and_refuses_unrelated_repo(world,tmp_path):
    life,root,repo,*_=world
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'x.py').write_text('x=1\n')
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    env={**os.environ,'GIT_AUTHOR_NAME':'fixture','GIT_AUTHOR_EMAIL':'fixture@localhost',
         'GIT_COMMITTER_NAME':'fixture','GIT_COMMITTER_EMAIL':'fixture@localhost'}
    subprocess.run(['git','-C',str(repo),'commit','-qm','fixture'],check=True,env=env)
    result=life.dispatch_task('orbit','ctx-task',repo,'Inspect scheduling',verify='true',dry_run=True)
    assert result['status']=='dry_run' and result['worker']=='claude_code'
    assert 'untrusted' in str(result['launch_argv']).lower()
    with pytest.raises(ValueError):life.dispatch_task('orbit','foreign',tmp_path,'Inspect',verify='true',dry_run=True)


def test_new_project_proposal_uses_canonical_notes_not_second_registry(world):
    life,root,*_=world
    p=capture(life,project=None,kind='project',project_spec={'name':'Robotics Lab','aliases':['Robo'],
                  'scope':'Manipulation experiments','status':'seed'})
    life.ready(p['id']);reviewer_approve(life,p['id']);life.gate.apply(p['id']);life.reconcile(p['id'])
    assert life.projects.resolve('Robo')['status']=='matched'


def test_export_preview_is_outside_canonical_vault_and_contains_review_diff(world):
    life,root,*_=world
    p=capture(life);life.ready(p['id']);out=life.export(p['id'])
    assert Path(out['directory']).is_relative_to(life.state)
    assert (Path(out['directory'])/'review.md').exists()
    preview=life.navigation()
    assert 'Pending' in Path(preview).read_text() and p['id'] in Path(preview).read_text()
    assert not (root/p['target']).exists()


def test_no_canonical_mutation_api_and_live_vault_state_refused(world):
    life,root,*_=world
    from agentos.knowledge_lifecycle import Lifecycle
    assert not hasattr(life,'approve') and not hasattr(life,'commit')
    with pytest.raises(ValueError):Lifecycle(life.cfg,vault=root,state=root/'wiki/unsafe')


def test_cli_draft_ready_export_reject_and_safe_errors(world,tmp_path):
    life,root,*_=world
    from agentos.cli import main
    record=tmp_path/'capture.json'
    record.write_text(json.dumps(dict(project='orbit',kind='idea',summary='CLI orbital fixture',
                    evidence=[{'kind':'user_statement','locator':'session:cli'}],authorized=True)))
    env={**os.environ,'AGENTOS_VAULT':str(root),'AGENTOS_STATE_DIR':str(tmp_path/'cli-state')}
    def cli(*args):
        return subprocess.run([sys.executable,'-m','agentos.cli','knowledge',*args],env=env,
                              capture_output=True,text=True)
    r=cli('capture','--input',str(record));assert r.returncode==0,r.stderr
    pid=json.loads(r.stdout)['id']
    assert cli('ready',pid).returncode==0
    assert cli('export',pid).returncode==0
    assert cli('reject',pid,'--reason','Not pursuing').returncode==0
    assert cli('approve',pid).returncode!=0
    bad=tmp_path/'bad.json';bad.write_text('{ invalid')
    r=cli('capture','--input',str(bad));assert r.returncode==2 and 'Traceback' not in r.stderr


def test_inline_broken_or_cross_project_link_is_rejected(world):
    life,root,*_=world
    note(root,'wiki/concepts/Foreign.md','other','Different scope.')
    for link in ['[[Missing note]]','[[Foreign]]']:
        with pytest.raises(ValueError,match='link|project'):
            capture(life,summary='Compare orbital scheduling with '+link)


def test_unverified_frontmatter_cannot_promote_a_claim_to_verified_fact(world):
    life,root,*_=world
    note(root,'wiki/concepts/Unsupported.md','orbit','Unsupported polar coverage claim.',
         evidence_status='verified',authority='primary',review_state='reviewed')
    c=life.context('orbit','unsupported polar coverage',budget=6000)
    assert c['prior_notes'] and c['verified_facts']==[]


def test_actor_and_task_identity_are_part_of_capture_idempotency(world):
    life,*_=world
    a=capture(life,origin={'actor':'codex','kind':'worker_report','task_id':'first'})
    b=capture(life,origin={'actor':'codex','kind':'worker_report','task_id':'second'})
    assert a['id']!=b['id']


def test_tampered_engine_receipt_is_refused(world):
    life,root,*_=world
    p=capture(life);life.ready(p['id']);reviewer_approve(life,p['id']);life.gate.apply(p['id'])
    path=root/'.vault-meta/transactions'/p['id']/'journal.json';j=json.loads(path.read_text())
    j['input_bundle_sha256']='0'*64;path.write_text(json.dumps(j))
    with pytest.raises(ValueError,match='journal|bundle'):
        life.reconcile(p['id'])


def test_project_read_dependency_change_after_approval_blocks_engine_apply(world):
    from agentos.knowledge import GateError
    life,root,*_=world
    p=capture(life);life.ready(p['id']);reviewer_approve(life,p['id'])
    page=root/'wiki/projects/Orbit.md';page.write_text(page.read_text()+'\nScope changed by human\n')
    with pytest.raises(GateError):life.gate.apply(p['id'])
    assert not (root/p['target']).exists()


@pytest.mark.parametrize('kind,operation',[('decision','new'),('experiment','new'),('research_question','new'),
                                         ('hypothesis','new'),('rejected_alternative','new'),('idea','link'),
                                         ('decision','supersede'),('decision','contradict')])
def test_supported_proposal_types_commit_through_existing_engine(world,kind,operation):
    life,root,*_=world
    target=None
    if operation!='new':
        note(root,'wiki/concepts/Prior.md','orbit','Preserved earlier decision.')
        target='wiki/concepts/Prior.md'
    p=capture(life,kind=kind,operation=operation,target=target,related=['wiki/projects/Orbit.md'])
    life.ready(p['id']);reviewer_approve(life,p['id']);life.gate.apply(p['id'])
    assert life.reconcile(p['id'])['state']=='COMMITTED'


def test_existing_gate_rolls_back_interrupted_apply_and_retry_is_idempotent(world):
    life,root,*_=world
    p=capture(life);life.ready(p['id']);reviewer_approve(life,p['id'])
    # Exercise upstream's deterministic failure injection in a separate interpreter.
    script='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from claude_obsidian.transaction import apply_bundle
bundle=json.loads(Path(sys.argv[3]).read_text())
try:
    apply_bundle(Path(sys.argv[2]),bundle,approved_plan_sha256=sys.argv[4],fail_after=2)
except RuntimeError:
    sys.exit(17)
'''
    meta=json.loads((life.gate.proposal_dir/(p['id']+'.meta.json')).read_text())
    result=subprocess.run([sys.executable,'-c',script,str(life.gate.cli.parent.parent),str(root),
                           meta['bundle'],meta['approval_sha256']],capture_output=True,text=True)
    assert result.returncode==17,result.stderr
    assert not (root/p['target']).exists()
    assert life.reconcile(p['id'])['state']=='APPROVED'
    life.gate.apply(p['id'])
    assert life.reconcile(p['id'])['state']=='COMMITTED'


def git_fixture(repo):
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'x.py').write_text('x=1\n')
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    env={**os.environ,'GIT_AUTHOR_NAME':'fixture','GIT_AUTHOR_EMAIL':'fixture@localhost',
         'GIT_COMMITTER_NAME':'fixture','GIT_COMMITTER_EMAIL':'fixture@localhost'}
    subprocess.run(['git','-C',str(repo),'commit','-qm','fixture'],check=True,env=env)


def test_synthetic_worker_retry_receives_context_and_uses_existing_leases(world):
    from agentos import worktree
    life,root,repo,*_=world
    git_fixture(repo)
    calls=[]
    def runner(launch,**kw):
        calls.append(launch)
        assert 'untrusted' in str(launch['argv']).lower()
        return {'returncode':1 if len(calls)==1 else 0,'latency_ms':1}
    kwargs=dict(verify='true',dry_run=False,runner=runner,worktree_root=repo.parent/'worktrees')
    first=life.dispatch_task('orbit','retry-fixture',repo,'Inspect orbital scheduling',**kwargs)
    assert first['status']=='retryable'
    assert worktree.holder(first['worktree']) is None
    second=life.dispatch_task('orbit','retry-fixture',repo,'Inspect orbital scheduling',**kwargs)
    assert second['status']=='done' and second['exit_state']=='success' and len(calls)==2
    assert first['worktree']==second['worktree'] and worktree.holder(second['worktree']) is None


def test_existing_active_lease_is_not_stolen(world):
    from agentos import worktree
    life,root,repo,*_=world
    git_fixture(repo)
    life.dispatch_task('orbit','held-task',repo,'Inspect orbit',verify='false',dry_run=False,
                       runner=lambda *a,**k:{'returncode':1},worktree_root=repo.parent/'worktrees')
    from agentos.taskstate import TaskStore
    wt=Path(TaskStore(life.cfg).get('held-task').state['checkout'])
    worktree.acquire(wt,'codex','other-active-owner')
    with pytest.raises(worktree.LeaseError):
        life.dispatch_task('orbit','held-task',repo,'Inspect orbit',verify='true',dry_run=False,
                           runner=lambda *a,**k:pytest.fail('must not start a worker'),worktree_root=repo.parent/'worktrees')
    assert worktree.holder(wt)['task_id']=='other-active-owner'


def test_codex_fallback_context_matches_existing_route(world):
    life,root,repo,*_=world
    git_fixture(repo)
    result=life.dispatch_task('orbit','codex-plan',repo,'Inspect orbit',verify='true',dry_run=True,
                              health={'providers':{'claude_subscription':False}})
    assert result['worker']=='codex'
    context=json.loads((life.state/'contexts/codex-plan.json').read_text())
    assert context['worker']=='codex'


def test_context_and_preview_state_symlink_cannot_write_vault(world):
    life,root,repo,*_=world
    life.state.mkdir(parents=True,exist_ok=True)
    (life.state/'navigation.md').symlink_to(root/'wiki/index.md')
    before=digest(root/'wiki/index.md')
    with pytest.raises(ValueError):life.navigation()
    assert digest(root/'wiki/index.md')==before


@pytest.mark.parametrize('name',['capture.md','review.md'])
def test_export_leaf_symlink_cannot_write_canonical_note(world,name):
    life,root,*_=world
    p=capture(life);life.ready(p['id']);export=life.export(p['id'])
    target=Path(export['directory'])/name;target.unlink();target.symlink_to(root/'wiki/index.md')
    before=digest(root/'wiki/index.md')
    with pytest.raises(ValueError):life.export(p['id'])
    assert digest(root/'wiki/index.md')==before


def test_concurrent_canonical_edit_during_ready_is_not_adopted_as_stale_content_base(world,monkeypatch):
    import agentos.knowledge_lifecycle as module
    life,root,*_=world
    p=capture(life);original=module.ingest_source_writes
    def concurrent(*args,**kw):
        result=original(*args,**kw)
        index=root/'wiki/index.md';index.write_text(index.read_text()+'\nHuman concurrent addition\n')
        return result
    monkeypatch.setattr(module,'ingest_source_writes',concurrent)
    with pytest.raises(ValueError,match='stale'):life.ready(p['id'])
    assert 'Human concurrent addition' in (root/'wiki/index.md').read_text()


def test_tampered_journal_hash_cannot_authorize_modified_output(world):
    life,root,*_=world
    p=capture(life);life.ready(p['id']);reviewer_approve(life,p['id']);life.gate.apply(p['id'])
    note=root/p['target'];note.write_text(note.read_text().replace('Try orbital','Unauthorized changed orbital'))
    path=root/'.vault-meta/transactions'/p['id']/'journal.json';j=json.loads(path.read_text())
    for w in j['writes']:
        if w['path']==p['target']:w['new_sha256']=digest(note)
    path.write_text(json.dumps(j))
    with pytest.raises(ValueError,match='approval|expanded|journal'):life.reconcile(p['id'])


def test_inline_link_is_a_pinned_read_dependency(world):
    life,root,*_=world
    linked=note(root,'wiki/concepts/Previous.md','orbit','Existing orbit decision.')
    p=capture(life,summary='Try scheduling based on [[Previous]].')
    linked.write_text(linked.read_text()+'\nChanged decision\n')
    with pytest.raises(ValueError,match='stale'):life.ready(p['id'])


def test_sensitive_source_locator_never_enters_worker_context(world):
    life,root,*_=world
    note(root,'wiki/concepts/Source.md','orbit','Useful polar coverage result.')
    path=root/'wiki/meta/ledgers/source-ledger.json';d=json.loads(path.read_text())
    d['sources']['src-sensitive']={'origin':{'locator':'https://example.test/?api_key=private-value'},
                                 'pages':['wiki/concepts/Source.md']};path.write_text(json.dumps(d))
    c=life.context('orbit','polar coverage',budget=6000)
    assert 'private-value' not in json.dumps(c)


def test_unknown_worker_success_without_artifact_is_not_an_attested_success(world):
    life,*_=world
    r=life.ingest_result('orbit',{'task_id':'fabricated','status':'done','exit_state':'success','worker':'codex',
                                'verify':{'passed':True}},summary='Claimed success',
                         evidence=[{'kind':'user_statement','locator':'session:assertion'}],authorized=True)
    assert r['status']=='unverified_external_report' and r['proposal'] is None


def test_sensitive_json_origin_is_refused(world):
    life,*_=world
    with pytest.raises(ValueError,match='sensitive'):
        capture(life,origin={'actor':'hermes','password':'not-for-knowledge'})
    assert life.list()==[]


def test_project_changes_since_honors_timezone_offsets(world,monkeypatch,capsys):
    import agentos.knowledge_lifecycle as module
    from agentos.cli import main
    life,root,*_=world
    monkeypatch.setattr(module,'now',lambda:'2026-11-13T12:00:00+00:00')
    monkeypatch.setenv('AGENTOS_VAULT',str(root))
    p=capture(life)
    assert main(['knowledge','changes','--project','orbit','--since','2026-11-13T14:00:00+03:00'])==0
    result=json.loads(capsys.readouterr().out)
    assert p['id'] in [x['id'] for x in result['proposals']]


def test_real_engine_process_interruption_requires_recovery_then_recovers(world):
    life,root,repo,engine=world
    p=capture(life);life.ready(p['id']);reviewer_approve(life,p['id'])
    meta=json.loads((life.gate.proposal_dir/(p['id']+'.meta.json')).read_text())
    script='''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from claude_obsidian.transaction import apply_bundle
apply_bundle(Path(sys.argv[2]),Path(sys.argv[3]),approved_plan_sha256=sys.argv[4],
             progress=lambda path,index:os._exit(23))
'''
    r=subprocess.run([sys.executable,'-c',script,str(life.gate.cli.parent.parent),str(root),
                      meta['bundle'],meta['approval_sha256']],capture_output=True,text=True)
    assert r.returncode==23,r.stderr
    interrupted=life.reconcile(p['id'])
    assert interrupted['state']=='APPROVED' and interrupted['recovery_required']
    engine('transaction','recover','--vault',str(root),'--timeout','1','--stale-after','0')
    assert not (root/p['target']).exists()
    life.gate.apply(p['id'])
    assert life.reconcile(p['id'])['state']=='COMMITTED'


def test_export_parent_swap_cannot_follow_symlink_into_canonical_wiki(world,monkeypatch):
    import agentos.knowledge_lifecycle as module
    life,root,*_=world
    p=capture(life);life.ready(p['id']);out=life.export(p['id']);directory=Path(out['directory'])
    original=module.atomic_text
    swapped=[]
    def swap(path,text):
        if not swapped:
            directory.rename(directory.with_name(directory.name+'-saved'))
            directory.symlink_to(root/'wiki/projects',target_is_directory=True);swapped.append(True)
        return original(path,text)
    monkeypatch.setattr(module,'atomic_text',swap)
    with pytest.raises((ValueError,OSError)):life.export(p['id'])
    assert swapped and not (root/'wiki/projects/handoff.json').exists()
    assert not (root/'wiki/projects/capture.md').exists()


@pytest.mark.parametrize('reviewer',[None,'','  '])
def test_missing_reviewer_identity_cannot_approve(world,reviewer):
    life,*_=world
    p=capture(life);life.ready(p['id']);meta=reviewer_stage(life,p['id'])
    path=life.gate.approval_dir/('knowledge-'+p['id']+'.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'operation_id':p['id'],'proposer':p['origin']['actor'],
                               'reviewer':reviewer,'approval_sha256':meta['approval_sha256'],
                               'human_approval_ref':'human:test-approval'}))
    with pytest.raises(ValueError,match='reviewer'):life.reconcile(p['id'])
