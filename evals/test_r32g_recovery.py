"""Regression coverage for recovery defects; thresholds match Phase 2A unchanged."""
import math
from pathlib import Path
import pytest
from agentos import systemone_calibration as K
from agentos import systemone_gates as G


def test_platt_actual_development_overflow():
    res = G.load(Path(__file__).parents[1] / 'audit/systemone-eval-r3.2g/dev/B2-raw.json')
    ps = K.points(res, 'described')
    m = K.fit_platt(ps)
    assert all(math.isfinite(m[k]) for k in ('a', 'b'))
    probs = [K.apply_map(m, c) for c, _ in ps]
    assert all(0 <= p <= 1 for p in probs)
    def loss(probs):
        return -sum(y*math.log(max(p, 1e-15))+(1-y)*math.log(max(1-p, 1e-15)) for p, (_,y) in zip(probs,ps))
    assert loss(probs) < loss([c for c,_ in ps])


@pytest.mark.parametrize('ps', [[(0,0),(1,1)]*20, [(0.5,0),(0.5,1)]*20, [(1,0)]*20, [(0,1)]*20])
def test_platt_extreme_constant_and_single_class(ps):
    m=K.fit_platt(ps)
    assert all(math.isfinite(K.apply_map(m,c)) for c in (0,.5,1))
    assert K.apply_map({'kind':'platt','a':1e6,'b':0},0) == 0
    assert K.apply_map({'kind':'platt','a':1e6,'b':0},1) == 1


def test_isotonic_ties_order_invariant_and_no_rounded_boundary():
    ps=[(.5000001,1),(.5000001,0),(.5000002,1),(.9,0),(.9,1)]
    m=K.fit_isotonic(ps)
    assert m == K.fit_isotonic(list(reversed(ps)))
    assert m['x'][0] == .5000001
    assert K.apply_map(m,.5000001) == .5
    assert m['y'] == sorted(m['y'])
    assert K.apply_map(m,0) == m['y'][0] and K.apply_map(m,1) == m['y'][-1]


def test_missing_gate_evidence_is_unknown():
    out=G.gates({},None)
    assert out['unknown'] == [f'G{i}' for i in range(1,8)]
    assert not out['all_pass'] and not out['no_go_gate_failed']
    for i in range(1,8):
        assert out[f'G{i}']['pass'] is None


def test_g7_canonical_key_and_threshold_and_g6_memory_required():
    def run(p):
        return G.gates({'probes':{'abstention':p}},None)
    assert run({'precision_of_abstention_on_escalate_gold':.5})['G7']['pass'] is True
    assert run({'precision_of_abstention_on_escalate_gold':.4999})['G7']['pass'] is False
    assert run({'precision':.9})['G7']['pass'] is None
    assert G.gates({},0,{'warm_latency_ms':{'p95':1}})['G6']['pass'] is None
    assert G.gates({},0,{'warm_latency_ms':{'p95':1000}},7)['G6']['pass'] is True
    assert G.gates({},0,{'warm_latency_ms':{'p95':1001}})['G6']['pass'] is False


def test_store_preserves_crlf_and_detects_corruption(tmp_path):
    from agentos.contextgate import Store
    s=Store(tmp_path); text='a\r\nb\r\nc\r'
    sha=s.put(text)
    assert s.get(sha)==text
    (tmp_path/sha).write_text('tampered')
    with pytest.raises(ValueError): s.get(sha)


def test_cache_does_not_reuse_rule_across_different_task_state(tmp_path):
    from dataclasses import replace
    from agentos import rulecache as R, systemone as S
    req=S.SystemOneRequest('coding',(S.Question('worker','choose','who'),),('a','b'),{'summary':'tests'})
    cache=R.RuleCache(tmp_path/'cache.yaml')
    r=cache.propose(req,S.PolicyOrderBackend().decide(req),'hash','fixture')
    with pytest.raises(ValueError): cache.approve(r['id'],'human:')
    cache.approve(r['id'],'human:fixture')
    assert cache.lookup(req,'hash')
    for changed in (replace(req,state={'summary':'architecture'}),replace(req,resource_state={'mac':False}),replace(req,allow_abstain=True)):
        assert cache.lookup(changed,'hash') is None


def test_pipeline_rejects_error_abstention_and_conflicting_reply():
    from agentos import systemone as S, systemone_adapter as A
    from agentos.systemone_pipeline import PipelineBackend
    class Runtime:
        reply={}
        def ask(self,payload,timeout):
            return {'v':1,'id':'worker','confidence':.9,**self.reply}
    rt=Runtime(); be=PipelineBackend(A.AdapterBackend('fake',rt),strategy='per-option')
    req=S.SystemOneRequest('coding',(S.Question('worker','choose','who'),),('a','b'))
    rt.reply={'abstain':True,'error':'failure'}
    assert S.system_one(req,be).reason_code=='backend-error'
    rt.reply={'abstain':True,'choice':'a'}
    assert S.system_one(req,be).reason_code=='malformed-output'


def test_wake_errors_and_approval_in_non_alert_events():
    from agentos import wakegate as W
    for event in (W.Event('webhook','deployment failed'),W.Event('email','approval required'),W.Event('email','işlem başarısız')):
        assert W.gate(event,W.WaitState('reply'),None).reason.startswith('rule:')


def test_pruner_protects_security_paths_and_carriage_return_error(tmp_path):
    from agentos.contextgate import Store
    from agentos.toolpruner import prune
    output='start\n'+'noise\n'*1200+'error E1001 before redraw\rprogress 90%\nnever disclose credentials\nconfig/settings.yaml\n'+'noise\n'*1200
    r=prune(output,Store(tmp_path))
    assert all(s in r.view for s in ('error E1001','never disclose credentials','config/settings.yaml'))
    assert r.sha256 in r.view


def test_compat_rejects_reserved_ids():
    from agentos import systemone_compat as X
    with pytest.raises(X.CompatError):
        X.to_requests({'questions':{'_escalation_0':{'type':'choice','criteria':{'a':None}}}},['a'])


def test_acceptance_harness_fails_closed():
    from agentos.module_eval import acceptance
    assert not acceptance({})
    assert not acceptance({'false_negatives':1})
    assert not acceptance({'false_drops':0,'recovery_exact_all':False})
    assert not acceptance({'essential_lost':1,'recovery_exact_all':True})
