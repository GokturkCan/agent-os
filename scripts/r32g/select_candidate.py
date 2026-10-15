"""Apply preregistered development selection, never held-out outcomes."""
import json
from pathlib import Path
from agentos import systemone_gates as G
root=Path('audit/systemone-eval-r3.2g');rows={}
for name in ('A','B1','B2','B2-raw','B3','B3-raw'):
 res=G.load(root/'dev-recovery'/f'{name}.json');bench=G.load(root/'performance'/f'{name}-bench.json')
 mem=bench['memory']['worker_rss_mib_peak_sampled']/1024
 rows[name]=G.row(name,res,.714,bench=bench,memory_gib=mem)
eligible=[r for r in rows.values() if r['gates']['G1']['pass'] is True and r['gates']['G6']['pass'] is True]
assert eligible,'No development candidate meets mandatory G1/G6'
def key(r):return (sum(r['gates'][g]['pass'] is True for g in ('G2','G3','G4','G5','G7')),r['acceptable'],-r['calls_per_decision'])
winner=max(eligible,key=key)
result={'rule':'G1 and G6 required; most G2/G3/G4/G5/G7 passes; then described acceptable; then fewer calls',
 'label_prior_preregistered':.714,'label_prior_measured':G.load(root/'dev-recovery/label-prior.json')['variants']['bare']['layer1_decision_quality']['acceptable_rate'],
 'selected':winner['name'],'spec':G.load(root/'dev-recovery'/f"{winner['name']}.json")['backend'],'rows':rows,
 'selection_is_not_production_go':True,'memory_gate_measure':'peak sampled worker RSS (original gate); physical footprint reported separately'}
p=root/'candidate-selection.json'
assert not p.exists(),'refuse overwrite'
p.write_text(json.dumps(result,indent=2)+'\n');print(result['selected'],result['spec'])
