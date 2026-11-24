import json,sys,statistics
import torch
from pathlib import Path
from safetensors import safe_open
from pairs import rows,tracks,target_track,shape
torch.set_num_threads(1)
f=Path(sys.argv[1]); pairs=json.loads(Path(__file__).with_name('pairs.json').read_text());tr=tracks(f)
m=Path('/models/Qwen2.5-7B-Instruct');weights=json.loads((m/'model.safetensors.index.json').read_text())['weight_map']
with safe_open(str(m/weights['lm_head.weight']),framework='pt',device='cpu') as handle:
    h=handle.get_slice('lm_head.weight')
    w=torch.stack([h[i:i+1][0] for i in [448,323]]).double()
def load(r):
 return torch.load(next(f.glob('cmpl-'+r['id']+'-*.pt')),weights_only=True)
rr=rows(f/'replay.jsonl');ref=load(rr[0]); out=[]
def first_bool(x):
 pos=x.nonzero()
 return int(pos[0])+1 if pos.numel() else None
for r in rr:
 try: d=load(r)
 except StopIteration:continue
 assert list(d['steps'])==list(range(1,33)),(r['label'],d['steps'])
 l=d['logits'];hh=d['hidden']; idx=29
 t=hh[idx].double()@w.T
 source=next((x for p in pairs for k in ('failed','control') if (x:=p[k])['id']==r['source']),None)
 a=target_track(tr[r['id'].split('-')[-1]])
 if source:
  ss=target_track(source['track'])
  aa=json.loads(json.dumps(a))
  score=[aa[0]==ss[0],shape(aa[0])==shape(ss[0]),sum(x==y for x,y in zip(aa,ss)),sum(shape(x)==shape(y) for x,y in zip(aa,ss))]
 else:score=None
 row=dict(label=r['label'],id=r['id'],mode=r['mode'],source=r['source'],replay_score=score,
    first_hidden=first_bool((hh!=ref['hidden']).any(-1)),first_logit=first_bool((l!=ref['logits']).any(-1)),first_token=next((i for i,(x,y) in enumerate(zip(r['output_ids'],rr[0]['output_ids']),1) if x!=y),None),
    output30=r['output_ids'][idx],scores30=l[idx,[448,323]].float().tolist(),precise30=t.tolist(),
    top30=l[idx].topk(4)[1].int().tolist(),max_hdiff1=(hh[0].float()-ref['hidden'][0].float()).abs().max().item(),
    max_ldiff1=(l[0].float()-ref['logits'][0].float()).abs().max().item())
 out.append(row)
 print(row['label'],row['output30'],row['first_hidden'],row['first_logit'],row['scores30'],[round(x,5) for x in t.tolist()],score)
(f/'scores.json').write_text(json.dumps(out,indent=2))
