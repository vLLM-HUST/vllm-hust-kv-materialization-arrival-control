"""Controlled transfer and arrival sweeps on the frozen 7,742-token discovery fixture."""
import asyncio
import json
from pathlib import Path
import random
import runpy
import statistics
import sys
import time
import uuid

import aiohttp

BASE_CODE = runpy.run_path(str(Path(__file__).with_name("run-contention.py")))
Run = BASE_CODE["Run"]
helpers = BASE_CODE["HELPERS"]
url = BASE_CODE["BASE"]
model = BASE_CODE["MODEL"]
receipt_pattern = BASE_CODE["RECEIPT"]
ROOT = Path("/root/kv-arrival-testset-20261122")
DIGEST = "60514ec2ed1f3ccff083d9077a884d1e2820a2b98830ba4ca4256c5a11fbb425"
SCANS = {
    "wide_ready": (4096, 0),
    "wide_delayed": (4096, 80),
    "tight_ready": (2048, 0),
    "tight_delayed": (2048, 80),
}
ARRIVALS = (-20, 230, 480, 730)
CUT = {"full": 4096, "local": 2048, "cold": 0}
LOCAL = 2048


class HTTP:
    def __init__(self, http, id, options):
        self.http, self.id, self.options = http, id, options

    def post(self, route, **kw):
        kw["json"]["request_id"] = self.id
        kw["json"]["kv_transfer_params"] = self.options
        kw["headers"]["X-Request-Id"] = self.id
        return self.http.post(route, **kw)


class BoundaryRun(Run):
    def read_audit(self):
        return [json.loads(line) for f in self.dest.glob("connector-*.jsonl")
                for line in f.read_text().splitlines() if line.endswith("}")]

    async def send(self, id, salt, tokens, budget, opts, deadline):
        await asyncio.sleep(max(0.0, deadline-time.perf_counter()))
        actual = time.time_ns()
        r = await helpers["request"](HTTP(self.http,id,opts),url+"/v1/completions",model,
                                     tokens,budget,salt,17)
        assert r.success,(id,r.error)
        return {"id":id, "arrival_ns":actual, "first_token_ns":actual+int(1e9*(r.first_token-r.start)),
                "ttft_ms":1000*(r.first_token-r.start), "output_ids":r.token_ids,
                "tpot_ms":1000*(r.last_token-r.first_token)/max(1,budget-1),
                "output_sha256":helpers["token_digest"](r.token_ids)}

    async def anchor(self):
        row = await self.sample(self.salt,self.prompt[:4097],8,{})
        assert row["counts"]["computed"]==4097,row
        for _ in range(40):
            if "Stored 4096 tokens" in (self.dest/"cache.log").read_text():
                break
            await asyncio.sleep(0.1)
        self.record("setup.jsonl",{"stage":"seed",**row})

    async def trial(self, arm, condition, phase, minimum=2176):
        cap, hold_ms = SCANS[condition]
        mode, arrivals = "idle", ARRIVALS
        await self.reset_local()
        prime = await self.sample(self.salt,self.prompt[:LOCAL+1],1,
                                  {"lmcache.kv41_arm":"2048","lmcache.max_offload_tokens":0})
        assert prime["counts"]["local_cache"]==0 and prime["counts"]["external_cache"]==2048
        assert prime["counts"]["computed"]==1
        planned_cut = CUT[arm]
        seed = uuid.uuid4().hex[:12]
        target_id = "kv41-target-"+seed
        target_salt = self.salt+"-cold" if arm=="cold" else self.salt
        opt={"lmcache.kv41_arm":str(planned_cut), "lmcache.max_offload_tokens":0,
             "lmcache.kv41_first_prefill_cap":cap,"lmcache.kv41_ready_hold_ms":hold_ms}
        with (self.dest/"cache.log").open() as f:
            f.seek(0,2)
            tag = await self.traffic(mode)
            t0 = time.perf_counter()+0.16
            background_options={"lmcache.kv41_arm":"0","lmcache.max_offload_tokens":0}
            tasks=[self.send(f"kv41-back-{seed}-{i}",self.salt+f"-background-{seed}-{i}",
                             self.prompt[:4097],16,background_options,t0+ms/1000)
                   for i,ms in enumerate(arrivals)]
            try:
                row,*back = await asyncio.gather(self.send(target_id,target_salt,self.prompt,32,opt,t0),*tasks)
            finally:
                await self.traffic("idle")
            reads = [[int(n),float(s)*1000] for n,s in receipt_pattern.findall(f.read())]
        local = 0 if arm=="cold" else LOCAL
        external = planned_cut-local
        # Engine-driven commits share request-session extras across TP ranks.
        # Depending on rank interleaving, one or both ranks emit an interval.
        # The scheduler supplies the per-request logical retrieved-token count.
        receipt_counts = [n for n, _ in reads]
        if external:
            assert 1 <= len(receipt_counts) <= 2 and set(receipt_counts)=={external}, reads
        else:
            assert not receipt_counts, reads
        worker_receipts = reads
        reads = [[external, max(ms for _, ms in worker_receipts)]] if external else []
        all_rows = self.read_audit()
        decision = [r for r in all_rows if r["event"]=="decision" and
                    r["request"].startswith("cmpl-"+target_id+"-")]
        stages = {event: [x for x in all_rows
                          if x["event"]==event and x["request"].startswith("cmpl-"+target_id+"-")]
                  for event in ("external_submit","external_worker_ready","external_eligible","admission_budget")}
        forward = [b for b in all_rows if b["event"]=="forward_batch"]
        target_chunks = []
        target_prefill_ns = []
        co_prefill = 0
        for b in forward:
            request = next((r for r in b["requests"] if r["request"].startswith("cmpl-"+target_id+"-")),None)
            if request is not None and request["prefill"]:
                assert not any(x.startswith("cmpl-"+target_id+"-") for x in b["preempted"])
                target_chunks.append(request["prefill"])
                target_prefill_ns.append(b["timestamp_ns"])
                co_prefill += sum(r["prefill"] for r in b["requests"] if r["request"]!=request["request"])
        prefixes = tuple("cmpl-"+b["id"]+"-" for b in back)
        bg_prefill_in_ttft = sum(r["prefill"] for b in forward
                                if row["arrival_ns"] <= b["timestamp_ns"] <= row["first_token_ns"]
                                for r in b["requests"] if r["request"].startswith(prefixes))
        bg_prefill_all = sum(r["prefill"] for b in forward for r in b["requests"]
                             if r["request"].startswith(prefixes))
        overlaps = {d:sum(r["bytes"] for r in all_rows if r["event"]=="copy_batch" and
                          r["tag"]==tag and r["device"]==d and
                          r["begin_ns"]<row["first_token_ns"] and r["end_ns"]>row["arrival_ns"])
                    for d in ("npu:0","npu:1")}
        row.update({"arm":arm,"condition":condition,"phase":phase,"cache_local":local,
                    "cache_external":external,"expected_prefill":len(self.prompt)-planned_cut,
                    "prefill_chunks":target_chunks,"copy_overlap_bytes":overlaps,
                    "cache_read":reads,"worker_retrieval_receipts":worker_receipts,"gate_min_external":minimum,
                    "causal_events":stages,"prefill_timestamps_ns":target_prefill_ns,
                    "background_tpot_ms":[b["tpot_ms"] for b in back],
                    "bg_prefill_in_ttft":bg_prefill_in_ttft,"co_batch_prefill":co_prefill,
                    "background_actual_offsets_ms":[(b["arrival_ns"]-row["arrival_ns"])/1e6 for b in back]})
        self.record("targets.jsonl",row)
        assert decision and {(a["local"],a["external"]) for a in decision}=={(local,external)},row
        assert sum(target_chunks)==len(self.prompt)-planned_cut,row
        assert [n for n,_ in reads]==([external] if external else []),row
        assert (all(overlaps.values()) if mode!="idle" else not any(overlaps.values())),row
        assert bg_prefill_all==len(arrivals)*4097,(condition,bg_prefill_all)
        assert stages["admission_budget"] and target_chunks[0]<=cap, row
        if external:
            submitted,=stages["external_submit"]
            ready,=stages["external_worker_ready"]
            eligible,=stages["external_eligible"]
            assert not ready["failed"] and submitted["timestamp_ns"]<=ready["timestamp_ns"],row
            assert eligible["timestamp_ns"]-ready["timestamp_ns"]>=hold_ms*1e6-10_000,row
            assert eligible["timestamp_ns"]<=target_prefill_ns[0],row
        else:
            assert not any(stages[k] for k in ("external_submit","external_worker_ready","external_eligible")),row
        return row


def result(blocks):
    d=[local["ttft_ms"]-full["ttft_ms"] for full,local in blocks]
    mean=statistics.mean(d)
    half=2.364624*statistics.stdev(d)/len(d)**0.5
    return {"pairwise_local_minus_full_ms":d,"mean_delta_ms":mean,"ci95_ms":[mean-half,mean+half],
            "means_ms":{arm:statistics.mean(pair[i]["ttft_ms"] for pair in blocks)
                        for i,arm in enumerate(("full","local"))},
            "prefill_chunks":{arm:[pair[i]["prefill_chunks"] for pair in blocks]
                               for i,arm in enumerate(("full","local"))},
            "mean_background_tpot_ms":{arm:statistics.mean(x for pair in blocks for x in pair[i]["background_tpot_ms"])
                                        for i,arm in enumerate(("full","local"))}}


async def main(dest):
    manifest=json.loads((ROOT/"prompt-manifest.json").read_text())
    fixture,=[r for r in manifest["fixtures"] if r["split"]=="discovery" and r["prompt_sha256"]==DIGEST]
    prompt=json.loads((ROOT/"discovery-token-ids.json").read_text())[fixture["id"]]
    assert len(prompt)==7742 and helpers["token_digest"](prompt)==DIGEST
    assert helpers["token_digest"](prompt[:4097])==fixture["seed_sha256"]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as http:
        r=BoundaryRun(http,dest,prompt)
        await r.traffic("idle")
        await r.anchor()
        ref=await r.trial("cold","wide_ready","reference")
        assert ref["output_sha256"]=="d7d526001c223b2bcd3bf6f3c31b0550bc21f9aaa43d5fc7929ccf6a625796d9"
        summary={"fixture":fixture,"reference_sha256":ref["output_sha256"],"conditions":SCANS,
                 "arrivals_ms":ARRIVALS,"qualification":{},"results":{}}
        expected=ref["output_ids"]
        p=dest/"intervention-summary.json"
        qualified=[]
        for condition in SCANS:
            evidence={}
            for arm in CUT:
                row=await r.trial(arm,condition,"qualification")
                diff=next((i for i,(a,b) in enumerate(zip(row["output_ids"],expected),1) if a!=b),None)
                evidence[arm]={"matches":diff is None,"first_difference":diff,"chunks":row["prefill_chunks"]}
            summary["qualification"][condition]=evidence
            if all(x["matches"] for x in evidence.values()):
                qualified.append(condition)
            p.write_text(json.dumps(summary,indent=2)+"\n")
            print("qualification",condition,evidence,flush=True)

        blocks={condition:[] for condition in qualified}
        for n in range(8):
            sequence=list(qualified)
            random.Random(7742+n).shuffle(sequence)
            for condition in sequence:
                pair={}
                for arm in (("full","local") if n%2==0 else ("local","full")):
                    pair[arm]=await r.trial(arm,condition,"timing")
                if any(x["output_ids"]!=expected for x in pair.values()):
                    print("timing output mismatch",condition,n,flush=True)
                    continue
                blocks[condition].append((pair["full"],pair["local"]))
                print("timing",condition,len(blocks[condition]),flush=True)
                if len(blocks[condition])==8:
                    summary["results"][condition]=result(blocks[condition])
            p.write_text(json.dumps(summary,indent=2)+"\n")


if __name__=="__main__":
    asyncio.run(main(Path(sys.argv[1])))
