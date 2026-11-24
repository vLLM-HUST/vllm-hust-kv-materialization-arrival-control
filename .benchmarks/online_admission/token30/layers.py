import json,sys
from pathlib import Path
from pairs import rows
import torch
torch.set_num_threads(1)
p=Path(sys.argv[1]);rs=rows(p/'replay.jsonl')
by={r['label']:r for r in rs};summary={}
def load(r,rank):
 return torch.load(next(p.glob('layers-cmpl-'+r['id']+f'-*-r{rank}.pt')),weights_only=True)
def delta(a,b):
 k=(a!=b).reshape(*a.shape[:3],-1).sum(-1)
 si=k.any((1,2)).nonzero();s=int(si[0]) if len(si) else None
 if s is None:return dict(step=None)
 ly=int(k[s].any(1).nonzero()[0])
 return dict(step=s+1,layer=ly,k_diff=int(k[s,ly,0]),v_diff=int(k[s,ly,1]),
             layer0_kv_diff=k[s,0].tolist(),max_abs_first_layer=(a[s,ly].float()-b[s,ly].float()).abs().max().item())
for which in (1,2):
 fail=by[f'{which}-failed-0'];control=by[f'{which}-control-0'];gold=rs[0]
 for tag,a,b in [('fail_vs_cold',fail,gold),('control_vs_cold',control,gold),('fail_vs_control',fail,control)]:
  v=[delta(load(a,i),load(b,i)) for i in range(2)]
  summary[f'{which}_{tag}']=v
  print(which,tag,v)
(p/'layer-compare.json').write_text(json.dumps(summary,indent=2))
