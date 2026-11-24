"""Release the uninstrumented timing run only after strict paired regression."""
import json
from collections import Counter
from pathlib import Path
from pairs import B,rows,tracks
import sys
folders=[Path(sys.argv[1]),Path(sys.argv[2])]
old,new=[rows(p/'replay.jsonl') for p in folders]
assert [r['label'] for r in old]==[r['label'] for r in new] and len(new)==26
source={x['id']:(k,x['track']) for pair in json.loads((B/'token30/pairs.json').read_text()) for k in ('failed','control') for x in [pair[k]]}
frozen=json.loads(Path('/root/kv-arrival-peer-decode-7742-20261124/summary.json').read_text())['blocks'][0]['refs']
for p,rs in zip(folders,[old,new]):
 actual=tracks(p)
 for r in rs:
  if r['mode']=='full':
   assert json.loads(json.dumps(actual[r['id'].split('-')[-1]]))==source[r['source']][1]
   assert set(r['read'])=={2048} and sum(r['chunks'])==3646 and len(r['peers'])==4
   # Reject a change that avoids or changes the actual KV restore.
   for rank in (0,1):
    h=next(p.glob('kv-cmpl-'+r['id']+'-*-r'+str(rank)+'.json')).read_bytes()
    seed=next(x for x in p.glob(f'kv-cmpl-*-r{rank}.json') if 'kv41-target' not in x.name)
    assert json.loads(h)==json.loads(seed.read_bytes())
  else: assert not r['read'] and sum(r['chunks'])==7742
  assert all(z==frozen['cold_peer'] for z in r['peers'])
  if p==folders[1] or not (r['mode']=='full' and source[r['source']][0]=='failed'):
   assert r['output_ids']==frozen['cold_target'],r['label']
  else:
   assert r['output_ids'][:29]==frozen['cold_target'][:29] and r['output_ids'][29]==323
print('Exact locked trajectory, checkpoint, output and background regression passed.',Counter(r['mode'] for r in new))
