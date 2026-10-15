"""Equivalent sequential local workloads; raw host resource evidence retained."""
import json,subprocess,time
from pathlib import Path
from agentos import config as C, systemone_bench as B, systemone_pipeline as P, module_eval as M, systemone_adapter as A
root=Path('audit/systemone-eval-r3.2g/performance');root.mkdir(exist_ok=True)
cfg=C.load()
def capture(argv,path):
 try:
  r=subprocess.run(argv,capture_output=True,text=True,timeout=45)
  path.write_text(r.stdout+r.stderr)
  return {'returncode':r.returncode,'path':str(path)}
 except Exception as exc:
  path.write_text(str(exc));return {'error':str(exc),'path':str(path)}
for name,spec in [('A','laya-mlx'),('B1','pipeline:laya-mlx:neutral:choice'),('B2','pipeline:laya-mlx:neutral:per-option'),('B2-raw','pipeline:laya-mlx:raw:per-option'),('B3','pipeline:laya-mlx:neutral:consistency'),('B3-raw','pipeline:laya-mlx:raw:consistency'),('D','openjev-2b')]:
 p=root/f'{name}-bench.json'
 if p.exists():raise RuntimeError(f'refuse overwrite {p}')
 print('START bench',name,flush=True)
 parts=spec.split(':'); base=parts[1] if spec.startswith('pipeline:') else spec
 be=B._fresh_backend(cfg,base)
 if spec.startswith('pipeline:'):be=P.PipelineBackend(be,neutral=parts[2]=='neutral',strategy=parts[3],name=spec)
 before=capture(['memory_pressure'],root/f'{name}-system-before.txt')
 try:
  result=B.run_benchmark(cfg,base,n=200,warmup=10,seed=1337,repeat=20,backend=be)
  result['backend']=spec
  if hasattr(be,'summary'):result['pipeline']=be.summary()
  result['resource_capture']={'before':before,
   'loaded':capture(['memory_pressure'],root/f'{name}-system-loaded.txt'),
   'vm_stat':capture(['vm_stat'],root/f'{name}-vm-stat.txt'),
   'footprint':capture(['footprint','-p',str(be.runtime.pid)],root/f'{name}-worker-footprint.txt') if be.runtime.pid else {'error':'no worker'},
   'ps':capture(['ps','-o','pid=,rss=,vsz=,%cpu=','-p',str(be.runtime.pid)],root/f'{name}-worker-ps.txt') if be.runtime.pid else {'error':'no worker'}}
 finally:be.close()
 p.write_text(json.dumps(result,indent=2)+'\n')
 print('DONE bench',name,flush=True)
for suite in M.EVALS:
 for backend in (('none',) if suite=='rulecache' else ('none','laya-mlx')):
  p=Path('audit/systemone-eval-r3.2g/modules-recovery')/f'{suite}-{backend}-final.json'
  if p.exists():raise RuntimeError(f'refuse overwrite {p}')
  try:res=M.EVALS[suite](cfg,backend)
  finally:A.close_all()
  res['acceptance_pass']=M.acceptance(res)
  res['token_measurement']='ceil(chars/4) estimate, not tokenizer-measured'
  p.write_text(json.dumps(res,indent=2,ensure_ascii=False)+'\n')
  print('DONE module',suite,backend,res['acceptance_pass'],flush=True)
