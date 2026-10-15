"""Sequential R3.2G development rerun; refuses to overwrite evidence."""
import json
from pathlib import Path
from agentos import config as C, systemone_eval as E, systemone_adapter as A
root=Path('audit/systemone-eval-r3.2g/dev-recovery'); root.mkdir(exist_ok=True)
specs={'A-plain':'laya-mlx','A':'pipeline:laya-mlx:raw:choice','B1':'pipeline:laya-mlx:neutral:choice',
 'B2':'pipeline:laya-mlx:neutral:per-option','B2-raw':'pipeline:laya-mlx:raw:per-option',
 'B3':'pipeline:laya-mlx:neutral:consistency','B3-raw':'pipeline:laya-mlx:raw:consistency','Null':'null',
 'label-prior':'baseline:label-prior'}
for name,spec in specs.items():
 p=root/f'{name}.json'
 if p.exists(): raise RuntimeError(f'refusing overwrite {p}')
 print('START',name,flush=True)
 try: res=E.run_eval(C.load(),spec)
 finally: A.close_all()
 p.write_text(json.dumps(res,indent=2,ensure_ascii=False)+'\n')
 print('DONE',name,flush=True)
