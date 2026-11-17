#!/usr/bin/env python3
"""Explicitly TEST-ONLY end-to-end demonstration using synthetic disposable data.

Requires the existing test environment. Never grants real-vault approval and never
starts a real coding model. The reviewer helper lives in tests, not production.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
import pytest
import test_knowledge_lifecycle as fixture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,help='New disposable directory, never an existing project/vault')
    args=parser.parse_args();work=Path(args.workspace).resolve()
    canonical=(Path.home()/'SecondBrain').resolve()
    if work.exists() or work==canonical or work.is_relative_to(canonical) or work==ROOT or work.is_relative_to(ROOT):
        parser.error('workspace must be a new directory outside real SecondBrain and Agent OS')
    work.mkdir(parents=True,mode=0o700)
    patch=pytest.MonkeyPatch()
    patch.setenv('AGENTOS_NODE_MSI','down');patch.setenv('AGENTOS_LIVE','0')
    try:
        life,vault,repo,_=fixture.world.__wrapped__(work,patch)
        env={**os.environ,'AGENTOS_VAULT':str(vault)}
        def cli(*argv):
            r=subprocess.run([sys.executable,'-m','agentos.cli','knowledge',*argv],env=env,
                              capture_output=True,text=True,cwd=ROOT,check=True)
            return json.loads(r.stdout)
        request=dict(project='orbit',kind='idea',summary='Investigate orbital window caching to bound scheduling latency.',
                     evidence=[{'kind':'user_statement','locator':'session:synthetic-demo-idea'}],
                     origin={'actor':'hermes','kind':'user_statement','session':'synthetic-demo-idea'},
                     authorized=True,confidence='user_statement')
        capture_file=work/'idea.json';capture_file.write_text(json.dumps(request))
        idea=cli('capture','--input',str(capture_file));pid=idea['id']
        cli('ready',pid);export=cli('export',pid)
        fixture.reviewer_approve(life,pid)  # Explicit independent TEST-ONLY human approval.
        life.gate.apply(pid);done=life.reconcile(pid)
        recalled=cli('context','--project','orbit','--objective','orbital window caching scheduling latency')
        assert done['state']=='COMMITTED' and idea['target'] in [x['path'] for x in recalled['sources']]
        results={'A_idea_lifecycle':{'passed':True,'proposal_id':pid,'state':done['state'],
                   'handoff':export['directory'],'recalled_path':idea['target'],'approval':'test-only explicit independent reviewer'}}
        fixture.note(vault,'wiki/decisions/Prior Orbital Decision.md','orbit','Use polar coverage before optimizing latency.',
                     record_kind='decision',authority='primary',review_state='reviewed',evidence_status='verified')
        fixture.ground_fixture_note(vault,'wiki/decisions/Prior Orbital Decision.md')
        context=life.context('orbit','polar coverage',budget=6000)
        assert context['prior_decisions'] and context['verified_facts']
        results['B_prior_knowledge']={'passed':True,'project_id':context['project']['id'],
                                     'source_paths':[x['path'] for x in context['sources']]}
        fixture.git_fixture(repo)
        seen=[]
        def synthetic_runner(launch,**kw):
            seen.append(launch);assert 'untrusted' in str(launch['argv']).lower()
            return {'returncode':0,'latency_ms':1}
        outcome=life.dispatch_task('orbit','demo-worker',repo,'Inspect orbital scheduling with prior context',
                                  verify='true',dry_run=False,runner=synthetic_runner,worktree_root=work/'worktrees')
        artifact=repo/'synthetic-result.txt';artifact.write_text('Synthetic runner: verification command exited zero.\n')
        ingested=life.ingest_result('orbit',outcome,summary='Synthetic worker exercised the scoped scheduling task.',
                       evidence=[{'kind':'artifact','locator':str(artifact),'sha256':fixture.digest(artifact)}],authorized=True)
        assert ingested['status']=='success' and ingested['proposal']['state']=='DRAFT'
        assert not (vault/ingested['proposal']['target']).exists()
        results['C_worker_ingestion']={'passed':True,'task_status':outcome['status'],
                                      'proposal_id':ingested['proposal']['id'],'runner':'synthetic; no model inference'}
        rejected=fixture.capture(life,summary='Rejected synthetic caching alternative.')
        life.ready(rejected['id']);before={str(p):fixture.digest(p) for p in (vault/'wiki').rglob('*') if p.is_file()}
        life.reject(rejected['id'],'Explicit synthetic rejection')
        assert before=={str(p):fixture.digest(p) for p in (vault/'wiki').rglob('*') if p.is_file()}
        results['D_rejection']={'passed':True,'state':'REJECTED','canonical_unchanged':True}
        stale=fixture.capture(life,summary='A stale synthetic proposal.');life.ready(stale['id'])
        index=vault/'wiki/index.md';index.write_text(index.read_text()+'\nConcurrent human fixture edit\n')
        try:fixture.reviewer_stage(life,stale['id'])
        except ValueError:pass
        else:raise AssertionError('Stale handoff was accepted')
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            ids=list(pool.map(lambda _:fixture.capture(life,summary='Concurrent idempotent capture.')['id'],range(8)))
        assert len(set(ids))==1 and 'Concurrent human fixture edit' in index.read_text()
        results['E_conflict_concurrency']={'passed':True,'stale_refused':True,'duplicate_captures':8,'unique_records':1}
        from agentos.selfimprove import verify_manifest
        assert verify_manifest()==[]
        results['F_preservation_scope']={'protected_manifest_valid':True,'real_vault_mutations':False,
                                       'real_worker_inference':False,'real_Hermes_conversation':False,
                                       'note':'Full regression and live read-only recall checked separately.'}
        results['preview']=life.navigation()
        (work/'results.json').write_text(json.dumps(results,indent=2))
        print(json.dumps(results,indent=2))
    finally:patch.undo()


if __name__=='__main__':main()
