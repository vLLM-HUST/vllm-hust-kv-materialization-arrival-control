"""Same-load phase sweep with separate endpoint calibration and paired policy replay."""
import asyncio
import itertools
import os
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
LEAD_MS = int(os.environ.get("KV41_LEAD_MS", "1800"))
OFFSETS={"before":tuple(LEAD_MS + 250*i for i in range(4)), "during":(-20,230,480,730)}
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
        if policy=="online":
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
                   peers=[{"id":b["id"],"actual_offset_ms":(b["arrival_ns"]-row["arrival_ns"])/1e6,"tpot":b["tpot_ms"],"same_batch":any(p.startswith("cmpl-"+b["id"]+"-") for p in peers)} for b in others])
        self.record("online.jsonl",row)
        return row

async def qualify_and_run(http, dest, fixture, prompt, historical):
    r=Replay(http,dest,prompt)
    await r.reset_local()
    await r.anchor()
    await r.reset_local()
    cold=await r.sample(r.salt+"-cold",prompt,32,{"lmcache.kv41_arm":"0","lmcache.max_offload_tokens":0})
    r.record("setup.jsonl",{"stage":"cold","fixture":fixture,**cold})
    assert cold["counts"]["computed"]==len(prompt) and len(cold["output_ids"])==32
    print("cold",len(prompt),cold["output_sha256"],cold["output_sha256"]==historical,flush=True)
    refs=cold["output_ids"]
    times={"full":[],"local":[]}
    valid=True
    for phase in OFFSETS:
        for order in (("full","local"),("local","full")):
            for a in order:
                x=await r.probe(a,phase,"calibration")
                valid &= x["output_ids"]==refs
                print("cal",len(prompt),phase,a,x["output_ids"]==refs,flush=True)
                times[a].append(x["ttft_ms"])
    minimum=2048 if statistics.mean(times["full"])<statistics.mean(times["local"]) else 2176
    actions=set()
    for phase in OFFSETS:
        for a in POLICIES:
            x=await r.probe(a,phase,"qualification",minimum)
            valid &= x["output_ids"]==refs
            if a=="online": actions.add(x["decision"]["used"])
            print("qual",len(prompt),phase,a,x["decision"]["used"],x["output_ids"]==refs,flush=True)
    if not valid or actions!={0,2048}:
        print("qualification closed",len(prompt),"exact",valid,"actions",sorted(actions),flush=True)
        return False
    for i,order in enumerate(itertools.permutations(POLICIES)):
        for phase in list(OFFSETS)[::1 if i%2==0 else -1]:
            for a in order:
                x=await r.probe(a,phase,"timing",minimum)
                if x["output_ids"]!=refs:
                    print("timing invalid",len(prompt),i,phase,a,flush=True)
                    return False
        print("paired epoch",len(prompt),i+1,flush=True)
    return True

async def main(dest):
    manifest=json.loads((ROOT/"prompt-manifest.json").read_text())
    discovery=json.loads((ROOT/"discovery-token-ids.json").read_text())
    fixtures=((DIGEST,"d7d526001c223b2bcd3bf6f3c31b0550bc21f9aaa43d5fc7929ccf6a625796d9"),
              ("3905b35bb3d018fcc50ba4a079f81b10a41f8fade921edf4f13fde9ad1974b1c",
               "7de7962da418aefc3e9e154a35b5a423eb277f045fa9d430a8c7d649cfe1373b"))
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as http:
        for digest,historical in fixtures:
            fixture,=[x for x in manifest["fixtures"] if x["split"]=="discovery" and x["prompt_sha256"]==digest]
            prompt=discovery[fixture["id"]]
            if len(prompt) != int(os.environ.get("KV41_PROMPT_TOKENS", "7742")):
                continue
            assert src["helpers"]["token_digest"](prompt)==digest
            if not await qualify_and_run(http,dest,fixture["id"],prompt,historical):
                raise SystemExit("Qualification or timing incomplete; see trial records")
            return
        raise ValueError("Expected discovery fixture of 4891 or 7742 tokens")
if __name__=="__main__":
    asyncio.run(main(Path(sys.argv[1])))
