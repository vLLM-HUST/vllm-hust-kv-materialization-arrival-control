import asyncio,json,runpy,sys,time,uuid
from pathlib import Path
import aiohttp
from pairs import B,tracks,target_track,match_score
src=runpy.run_path(str(B/'run-admission-intervention.py'));Base=src['BoundaryRun']
pairs=json.loads((B/'token30/pairs.json').read_text())
async def main(dest):
 m=json.loads((src['ROOT']/'prompt-manifest.json').read_text())
 fixture,=[x for x in m['fixtures'] if x['split']=='discovery' and x['prompt_sha256']==src['DIGEST']]
 prompt=json.loads((src['ROOT']/'discovery-token-ids.json').read_text())[fixture['id']]
 assert src['helpers']['token_digest'](prompt)==src['DIGEST']
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as http:
  r=Base(http,dest,prompt)
  await r.anchor()
  async def trial(label,source,mode,offsets):
   await r.reset_local()
   key=uuid.uuid4().hex[:12];tid='kv41-target-'+key
   bg={'lmcache.kv41_arm':'0','lmcache.max_offload_tokens':0}
   if mode!='cold':
    prime=await r.sample(r.salt,prompt[:2049],1,{'lmcache.kv41_arm':'2048','lmcache.max_offload_tokens':0})
    assert (prime['counts']['external_cache'],prime['counts']['computed'])==(2048,1)
   opts=bg if mode=='cold' else {'lmcache.kv41_policy':'full','lmcache.max_offload_tokens':0}
   if source is not None and mode=='full':
    idx=next(i for i,p in enumerate(pairs) if source in (p['control'],p['failed']))
    tag='failed' if pairs[idx]['failed']==source else 'control'
    bg['lmcache.kv30_plan']=opts['lmcache.kv30_plan']=str(idx)+':'+tag
    offsets=[-12,-6,4,8]
   start=time.perf_counter()+.16
   with (dest/'cache.log').open() as log:
    log.seek(0,2)
    row,*others=await asyncio.gather(r.send(tid,r.salt+'-'+key if mode=='cold' else r.salt,prompt,32,opts,start),
         *(r.send(f'kv41-back-{key}-{i}',r.salt+key+str(i),prompt[:4097],16,bg,start+ms/1000) for i,ms in enumerate(offsets)))
    counts=[int(n) for n,_ in src['receipt_pattern'].findall(log.read())]
   tr=tracks(dest)[key];batches=target_track(tr)
   chunks=[q[3] for ba in batches for q in ba if q[0]=='T' and q[3]]
   assert sum(chunks)==(7742 if mode=='cold' else 3646) and set(counts)==({2048} if mode=='full' else set()),(counts,chunks)
   if source and mode=='full':
    assert json.loads(json.dumps(tr))==source['track'],(label,len(tr),len(source['track']))
   row.update(label=label,source=source['id'] if source else None,mode=mode,read=counts,chunks=chunks,
             source_score=match_score(json.loads(json.dumps(tr)),source['track']) if source else None,
             peers=[o['output_ids'] for o in others])
   r.record('replay.jsonl',row)
   print(label,mode,row['output_ids'][29],row['source_score'],flush=True)
   return row
  await trial('cold-reference',None,'cold',[])
  for j in range(4):
   for i,pair in enumerate(pairs):
    for tag in ('failed','control') if j%2==0 else ('control','failed'):
     x=pair[tag]
     await trial(f'{i+1}-{tag}-{j}',x,'full',x['offsets'])
     if j in (0,2):await trial(f'{i+1}-{tag}-{j}-cold',x,'cold',x['offsets'])

  await trial('cold-final',None,'cold',[])
if __name__=='__main__':asyncio.run(main(Path(sys.argv[1])))
