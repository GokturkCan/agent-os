"""One-shot frozen v2 scoring; verify committed freeze before ANY model call."""
import hashlib,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from agentos import config as C,systemone_eval as E,systemone_adapter as A
root=Path('audit/systemone-eval-r3.2g');freeze=json.loads((root/'v2-freeze.json').read_text())
p=Path(freeze['path']);sha=hashlib.sha256(p.read_bytes()).hexdigest();assert sha==freeze['sha256']
committed=subprocess.check_output(['git','show','HEAD:'+str(p)])
assert hashlib.sha256(committed).hexdigest()==sha,'dataset not committed at HEAD'
committed_freeze=json.loads(subprocess.check_output(['git','show','HEAD:'+str(root/'v2-freeze.json')]))
assert committed_freeze==freeze,'freeze metadata not committed'
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
out=root/'v2';out.mkdir(exist_ok=True)
start=out/'inference-start.json';assert not start.exists(),'one-shot runner already started; inspect evidence before any rerun'
start.write_text(json.dumps({'freeze_commit':head,'sha256':sha,'started_utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
specs={'A':'laya-mlx','C':freeze['selected_pipeline'],'D':'openjev-2b','first':'baseline:first','last':'baseline:last','label-prior':'baseline:label-prior','random':'baseline:random','Null':'null'}
for name,spec in specs.items():
 file=out/f'{name}.json';assert not file.exists()
 print('START',name,datetime.now(timezone.utc).isoformat(),flush=True)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
 try:res=E.run_eval(C.load(),spec,dataset=p)
 finally:A.close_all()
 res['freeze_commit']=head
 file.write_text(json.dumps(res,indent=2,ensure_ascii=False)+'\n')
 print('DONE',name,datetime.now(timezone.utc).isoformat(),flush=True)
