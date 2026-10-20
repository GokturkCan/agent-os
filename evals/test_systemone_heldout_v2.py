"""Pre-inference v2 checks derive from config facts, not model output."""
import collections,hashlib,json
from pathlib import Path
from agentos import config as C,systemone_eval as E,systemone_options as O
P=Path(__file__).parent/'data/systemone-heldout-v2.yaml'

def test_v2_schema_languages_and_novel_summaries():
 d=E.load_dataset(P)
 assert len(d['cases'])==128
 assert collections.Counter(c['lang'] for c in d['cases'])=={'en':64,'tr':64}
 old=[c for p in (E.DATASET,E.HELDOUT) for c in E.load_dataset(p)['cases']]
 assert not {c['id'] for c in d['cases']} & {c['id'] for c in old}
 assert not {c['request']['state']['summary'] for c in d['cases']} & {c['request']['state'].get('summary') for c in old}

def test_v2_capability_risk_and_scope_labels():
 cfg=C.load();d=E.load_dataset(P)
 for c in d['cases']:
  r,g=c['request'],c['gold'];opts=r['eligible_options']
  info={**O.build(cfg,opts,r['required_capabilities']),**r.get('option_info_extra',{})}
  acc=set(g.get('acceptable',[]));forb=set(g.get('forbidden',[]))
  assert not acc&forb and acc<=set(opts)
  if r['risk']=='high':assert bool(g.get('escalate')) is (not r['state'].get('human_approval'))
  for o,x in info.items():
   if x.get('missing') or x.get('status')=='unavailable' or (r['state'].get('interactive') and x.get('interactive') is False):
    assert o not in acc
    assert g.get('escalate') or o in forb
  if r['required_capabilities'] and g.get('escalate'):
   assert all(info[o].get('missing') for o in opts)
  if c['category']=='review_independence':assert r['state']['primary_worker'] in forb
  if c['category']=='worker_failure':assert r['state']['previous_worker'] in forb

def test_v2_e2e_facts():
 d=E.load_dataset(P);r=E.run_e2e(C.load(),E._Baseline('first'),d)
 assert r['passed']==r['n'],r

def test_frozen_v2_hash_when_freeze_exists():
 f=Path(__file__).parents[1]/'audit/systemone-eval-r3.2g/v2-freeze.json'
 if f.exists():assert hashlib.sha256(P.read_bytes()).hexdigest()==json.loads(f.read_text())['sha256']
