"""Compare the actual projection interventions on the same hidden input."""
import json
from pathlib import Path
import torch
from pairs import B,rows
torch.set_num_threads(1)
def points(p):return {r['label']:r for r in rows(p/'replay.jsonl')}
a,b=B/'token30-locked-1',B/'token30-fp32-locked'
data=[]
for label,r in points(a).items():
 s=points(b)[label]
 x,y=[torch.load(next(p.glob(f"cmpl-{j['id']}-*.pt")),weights_only=True)
      for p,j in ((a,r),(b,s))]
 assert x['logits'].dtype==torch.bfloat16 and y['logits'].dtype==torch.float32,(x['logits'].dtype,y['logits'].dtype)
 ix=next((i for i,(t,u) in enumerate(zip(r['output_ids'],s['output_ids'])) if t!=u),31)
 eq=(x['hidden'][:ix+1]==y['hidden'][:ix+1]).all(-1).tolist()
 data.append(dict(label=label,through=ix+1,identical_hidden=all(eq),first_difference=next((i for i,v in enumerate(eq,1) if not v),None),
   bf16_448_323=x['logits'][29,[448,323]].float().tolist(),fp32_448_323=y['logits'][29,[448,323]].tolist()))
print([(v['label'],v['identical_hidden'],v['fp32_448_323']) for v in data if v['label'].endswith('failed-0')])
(b/'intervention.json').write_text(json.dumps(data,indent=2))
