import collections,json,os
from pathlib import Path
B=Path(os.environ.get('KV41_BENCHMARK_DIR',Path(__file__).resolve().parents[1]))
def rows(p):
 return [json.loads(l) for l in p.read_text().splitlines()]
def tracks(folder):
 bykey=collections.defaultdict(list)
 for f in folder.glob('connector-*.jsonl'):
  for e in rows(f):
   if e['event']!='forward_batch':continue
   rr=[q for q in e['requests'] if q['scheduled'] and '-kv41-' in q['request']]
   if not rr:continue
   keys={q['request'].split('-')[3] for q in rr}
   assert len(keys)==1,keys
   rr=[('T' if '-target-' in q['request'] else q['request'].split('-')[4],q['start'],q['scheduled'],q['prefill']) for q in rr]
   bykey[keys.pop()].append(sorted(rr))
 return bykey
def target_track(seq):return [batch for batch in seq if any(x[0]=='T' for x in batch)]
def shape(batch):return sorted((r[2],r[3]) for r in batch)
def match_score(a,b):
 t,u=map(target_track,(a,b))
 return (t[0]==u[0],shape(t[0])==shape(u[0]),sum(x==y for x,y in zip(t,u)),sum(shape(x)==shape(y) for x,y in zip(t,u)))
if __name__=='__main__':
 candidates=[]
 for i in range(1,5):
  p=B/f'peer-7742-paired-{i}';tr=tracks(p)
  for r in rows(p/'online.jsonl'):
   if r['phase']=='during' and r['decision']['used']:
    candidates.append(dict(block=i,id=r['id'],policy=r['policy'],offsets=[p['actual_offset_ms'] for p in r['peers']],exact=r['output_sha256'].startswith('d7d526'),track=tr[r['id'].split('-')[-1]]))
 pairs=[]
 for bad in [c for c in candidates if not c['exact']]:
  good=max((c for c in candidates if c['exact']),key=lambda c:match_score(bad['track'],c['track']))
  same=sum(target_track(c['track'])[0]==target_track(bad['track'])[0] for c in candidates if c['exact'])
  print(bad['block'],bad['id'],good['block'],good['id'],same,match_score(bad['track'],good['track']))
  for c in (bad,good):print(c['offsets'],target_track(c['track'])[0],len(target_track(c['track'])))
  pairs.append({'failed':bad,'control':good,'exact_prefill_controls':same})
 (B/'token30/pairs.json').write_text(json.dumps(pairs))
