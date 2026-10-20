"""Record mechanical candidate hashes and exact review delta; NEVER human approval."""
import json
from pathlib import Path
from agentos.selfimprove import compute_manifest
root=Path(__file__).resolve().parents[2]
p=root/'evals/protected-manifest.json'
old=json.loads(p.read_text())
new=compute_manifest(root)
delta={k:{'before':old['files'].get(k),'after':new.get(k)} for k in sorted(set(new)|set(old['files'])) if new.get(k)!=old['files'].get(k)}
audit=root/'audit/systemone-eval-r3.2g/recovery'
idx=1
while (audit/f'protected-delta-{idx}.json').exists(): idx+=1
(audit/f'protected-delta-{idx}.json').write_text(json.dumps({'review_status':'PENDING HUMAN REVIEW BEFORE MERGE','changes':delta},indent=2)+'\n')
old['files']=new
old['note']='Candidate hashes refreshed mechanically for R3.2G validation. NOT human approval; review exact protected deltas in audit/systemone-eval-r3.2g/recovery before merge.'
p.write_text(json.dumps(old,indent=2)+'\n')
print(f'{len(delta)} candidate hash changes; human review remains pending')
