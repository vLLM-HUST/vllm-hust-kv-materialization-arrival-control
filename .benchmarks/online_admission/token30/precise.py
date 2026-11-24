"""Evaluate higher-precision finalists on the captured, unchanged hidden rows."""
import json,sys
from pathlib import Path
import torch
from safetensors import safe_open
torch.set_num_threads(1)
f=Path(sys.argv[1]);rr=[json.loads(l) for l in (f/'replay.jsonl').read_text().splitlines()]
m=Path('/models/Qwen2.5-7B-Instruct');wmap=json.loads((m/'model.safetensors.index.json').read_text())['weight_map']
root=Path('/root/kv-arrival-testset-20261122');man=json.loads((root/'prompt-manifest.json').read_text())
fixture,=[r for r in man['fixtures'] if r['split']=='discovery' and r['prompt_tokens']==7742]
prompt=set(json.loads((root/'discovery-token-ids.json').read_text())[fixture['id']])
out=[]
with safe_open(str(m/wmap['lm_head.weight']),framework='pt',device='cpu') as sh:
 w=sh.get_slice('lm_head.weight'); cache={}
 for r in rr:
  d=torch.load(next(f.glob('cmpl-'+r['id']+'-*.pt')),weights_only=True);ids=r['output_ids']
  pred=[];ties=[];rawmatch=[];refine=[]
  seen=prompt.copy()
  for i,(l,h,token) in enumerate(zip(d['logits'],d['hidden'],ids)):
   # Capture candidates from across the vocabulary. Check the native
   # penalty model against actual engine decisions before interpreting.
   y,ix=l.topk(32); ix=ix.tolist()
   for k in ix:
    if k not in cache:cache[k]=w[k:k+1][0].double()
   v=torch.stack([cache[k] for k in ix])@h.double()
   factor=torch.tensor([1.05 if k in seen else 1.0 for k in ix],dtype=torch.float32)
   raw=y.float()/factor
   tie=[k for k,z in zip(ix,raw) if z==raw.max()]
   rawmatch.append(min(tie)==token);ties.append(tie if len(tie)>1 else [])
   v=v/factor
   pred.append(ix[v.argmax()]);refine.append(max(tie,key=lambda k:v[ix.index(k)].item()))
   seen.add(token)
  out.append(dict(label=r['label'],original=ids,precise=pred,refined=refine,ties=ties,native_reproduced=sum(rawmatch)))
 print([(r['label'],r['native_reproduced'],[(j+1,a,b) for j,(a,b) in enumerate(zip(r['original'],r['precise'])) if a!=b]) for r in out])
(f/'precise.json').write_text(json.dumps(out))
