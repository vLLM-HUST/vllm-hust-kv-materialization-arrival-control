"""Same-load phase sweep with separate endpoint calibration and paired policy replay."""
import asyncio
import itertools
import json
from pathlib import Path
import runpy
import statistics
import sys
import time
import uuid
import aiohttp

src=runpy.run_path(str(Path(__file__).with_name("run-admission-intervention.py")))
Base=src["BoundaryRun"]
ROOT=src["ROOT"]
DIGEST=src["DIGEST"]
# Identical background wave (4 arrivals spaced 250 ms). Shift target within that wave.
OFFSETS={"before":(1800,2050,2300,2550), "during":(-20,230,480,730)}
POLICIES=("online","gate","readiness")

class Replay(Base):
    async def probe(self, policy, phase, stage, minimum=2048):
        await self.reset_local()
        prime=await self.sample(self.salt,self.prompt[:2049],1,
                    {"lmcache.kv41_arm":"2048","lmcache.max_offload_tokens":0})
        assert prime["counts"]["external_cache"]==2048 and prime["counts"]["computed"]==1
        key=uuid.uuid4().hex[:12]
        target="kv41-target-"+key
        opts={"lmcache.kv41_policy":policy,"lmcache.kv41_min_external":minimum,
              "lmcache.max_offload_tokens":0}
        if policy=="peer":
            del opts["lmcache.kv41_policy"]
        bg={"lmcache.kv41_arm":"0","lmcache.max_offload_tokens":0}
        start=time.perf_counter()+0.15
        with (self.dest/"cache.log").open() as f:
            f.seek(0,2)
            row,*others=await asyncio.gather(
                self.send(target,self.salt,self.prompt,32,opts,start),
                *(self.send(f"kv41-back-{key}-{i}",f"{self.salt}-{key}-{i}",self.prompt[:4097],16,bg,start+offset/1000)
                  for i,offset in enumerate(OFFSETS[phase])))
            reads=[int(n) for n,_ in src["receipt_pattern"].findall(f.read())]
        events=self.read_audit()
        prefix="cmpl-"+target+"-"
        decisions=[e for e in events if e["event"]=="admission" and e["request"].startswith(prefix)]
        assert decisions, row
        dec=decisions[-1]
        assert (dec["local"],dec["verified"])==(2048,2048)
        assert ((reads and set(reads)=={2048}) if dec["used"] else not reads), reads
        chunks=[]
        peers=set()
        for e in events:
            if e["event"]!="forward_batch":continue
            r=next((r for r in e["requests"] if r["request"].startswith(prefix)),None)
            if r:
                if r["prefill"]:chunks.append(r["prefill"])
                peers.update(v["request"] for v in e["requests"] if v["request"].startswith("cmpl-kv41-back-"+key))
        assert sum(chunks)==len(self.prompt)-2048-dec["used"], chunks
        row.update(prompt_len=len(self.prompt),policy=policy,phase=phase,stage=stage,decision=dec,chunks=chunks,reads=reads,
                   peers=[{"id":b["id"],"actual_offset_ms":(b["arrival_ns"]-row["arrival_ns"])/1e6,"tpot":b["tpot_ms"],"output_ids":b["output_ids"],"same_batch":any(p.startswith("cmpl-"+b["id"]+"-") for p in peers)} for b in others])
        self.record("online.jsonl",row)
        return row

POLICIES = ("peer", "online", "gate", "readiness")
# Balanced Williams order, repeated twice per lifecycle. Rotate the
# first epoch across service restarts and reverse phase order each epoch.
ORDERS = ((0,1,3,2),(1,2,0,3),(2,3,1,0),(3,0,2,1))
async def main(dest, block):
    manifest=json.loads((ROOT/"prompt-manifest.json").read_text())
    fixture,=[x for x in manifest["fixtures"] if x["split"]=="discovery" and x["prompt_sha256"]==DIGEST]
    prompt=json.loads((ROOT/"discovery-token-ids.json").read_text())[fixture["id"]]
    assert len(prompt)==7742 and src["helpers"]["token_digest"](prompt)==DIGEST
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as http:
        r=Replay(http,dest,prompt)
        await r.reset_local()
        await r.anchor()
        gold=[]
        for label,seq,k in (("target",prompt,32),("peer",prompt[:4097],16)):
            await r.reset_local()
            cold=await r.sample(r.salt+"-cold-"+label,seq,k,{"lmcache.kv41_arm":"0","lmcache.max_offload_tokens":0})
            assert cold["counts"]["computed"]==len(seq) and len(cold["output_ids"])==k
            if label=="target":
                assert cold["output_sha256"]=="d7d526001c223b2bcd3bf6f3c31b0550bc21f9aaa43d5fc7929ccf6a625796d9"
            r.record("setup.jsonl",{"stage":"cold_"+label,**cold})
            gold.append(cold["output_ids"])
        for epoch in range(-1,8):
            order=ORDERS[(epoch+block)%4]
            for phase in list(OFFSETS)[::1 if (epoch+block)%2==0 else -1]:
                for i in order:
                    x=await r.probe(POLICIES[i],phase,"qualification" if epoch<0 else "timing",2048)
                    assert x["decision"]["policy"]==POLICIES[i]
                    assert x["output_ids"]==gold[0],(block,epoch,phase,POLICIES[i],"target")
                    assert all(y["output_ids"]==gold[1] for y in x["peers"]),(block,epoch,phase,POLICIES[i],"peer")
            print("block",block,"epoch",epoch,"exact",flush=True)
if __name__=="__main__":
    asyncio.run(main(Path(sys.argv[1]),int(sys.argv[2])))
