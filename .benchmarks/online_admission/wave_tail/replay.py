"""Paired endpoint discovery on frozen, independently seeded prompts."""
import asyncio
import json
import runpy
import sys
import time
import uuid
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
src = runpy.run_path(str(HERE.parent / "run-admission-intervention.py"))
from design import OFFSETS, choose, verify
NO_STORE = {"lmcache.max_offload_tokens": 0}
COLD = {**NO_STORE, "lmcache.kv41_arm": "0"}


def snapshot(folder):
    return {p: p.stat().st_size for p in folder.glob("connector-*.jsonl")}


def delta(folder, positions):
    for p in folder.glob("connector-*.jsonl"):
        with p.open() as f:
            f.seek(positions.get(p, 0))
            for line in f:
                if line.endswith("}\n"):
                    yield json.loads(line)


class Replay(src["BoundaryRun"]):
    async def probe(self, cell, phase, policy, epoch, gate):
        await self.reset_local()
        prime = await self.sample(self.salt, self.prompt[:2049], 1,
                                  {**NO_STORE, "lmcache.kv41_arm": "2048"})
        c = prime["counts"]
        assert (c["local_cache"], c["external_cache"], c["computed"]) == (0, 2048, 1), c
        key = uuid.uuid4().hex[:12]
        tid = "kv41-target-" + key
        opts = {**NO_STORE, "lmcache.kv41_min_external": gate}
        if policy != "peer":
            opts["lmcache.kv41_policy"] = policy
        wave_start = time.perf_counter() + .2
        start = wave_start + phase/1000
        pos = snapshot(self.dest)
        with (self.dest / "cache.log").open() as log:
            log.seek(0, 2)
            tasks = [self.send(tid, self.salt, self.prompt, 32, opts, start)]
            for i in range(4):
                bid = f"kv41-back-{key}-{i}"
                tasks.append(self.send(bid, bid, self.prompt[:4097], 16, COLD,
                                       wave_start + i*.25))
            out = await asyncio.gather(*tasks)
            reads = [int(n) for n, _ in src["receipt_pattern"].findall(log.read())]
        r, peers = out[0], out[1:5]
        ev = list(delta(self.dest, pos))
        prefix = "cmpl-" + tid + "-"
        ds = [e for e in ev if e["event"] == "admission" and e["request"].startswith(prefix)]
        assert ds
        d = ds[-1]
        used = d["used"]
        assert d["policy"] == policy and (d["local"], d["verified"]) == (2048,2048)
        assert used in (0,2048) and set(reads) == ({2048} if used else set()), reads
        if policy in ("full","local","gate"):
            assert used == (2048 if policy=="full" or (policy=="gate" and gate<=2048) else 0)
        sums = {p["id"]: 0 for p in peers}
        same = set()
        chunks = []
        for e in ev:
            if e["event"] != "forward_batch":
                continue
            target = next((q for q in e["requests"] if q["request"].startswith(prefix)), None)
            if target and target["prefill"]:
                chunks.append([target["start"], target["prefill"]])
            for q in e["requests"]:
                for bid in sums:
                    if q["request"].startswith("cmpl-"+bid+"-"):
                        sums[bid] += q["prefill"]
                        if target and q["scheduled"]:
                            same.add(bid)
        assert set(sums.values()) == {4097}, sums
        assert chunks[0][0] == 2048+used and sum(n for _,n in chunks) == len(self.prompt)-2048-used
        batches = [e for e in ev if e["event"] == "copy_batch"]
        actual = [(p["arrival_ns"]-peers[0]["arrival_ns"])/1e6 for p in peers]
        target_offset=(r["arrival_ns"]-peers[0]["arrival_ns"])/1e6
        exposure_ok = (not batches and abs(target_offset-phase)<15 and
                       all(abs(t-i*250)<15 for i,t in enumerate(actual)))
        for p in peers:
            p["same_batch"] = p["id"] in same
        exact = (r["output_ids"] == self.gold[0] and all(p["output_ids"]==self.gold[1] for p in peers))
        self.record("rows.jsonl", dict(cell=cell,phase=phase,epoch=epoch,policy=policy,gate=gate,
                    prime=c,decision=d,chunks=chunks,reads=reads,target=r,peers=peers,exact=exact,
                    target_offset_ms=target_offset,peer_offsets_ms=actual,exposure_ok=exposure_ok))


async def main(dest, length, stage, block, selection=None):
    root = src["ROOT"]
    fixtures = json.loads((root/"prompt-manifest.json").read_text())["fixtures"]
    fx, = [f for f in fixtures if f["split"]=="discovery" and f["prompt_tokens"]==length]
    prompt = json.loads((root/"discovery-token-ids.json").read_text())[fx["id"]]
    assert length in (4891,8544) and src["helpers"]["token_digest"](prompt)==fx["prompt_sha256"]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as http:
        r = Replay(http,dest,prompt)
        await r.reset_local()
        await r.anchor()
        assert "Stored 4096 tokens" in (dest/"cache.log").read_text()
        r.gold = []
        for name, seq, k in (("target",prompt,32),("peer",prompt[:4097],16)):
            await r.reset_local()
            gold = await r.sample(r.salt+"-cold-"+name, seq,k,COLD)
            c = gold["counts"]
            assert (c["local_cache"],c["external_cache"],c["computed"])==(0,0,len(seq)) and len(gold["output_ids"])==k
            r.gold.append(gold["output_ids"])
            r.record("setup.jsonl",dict(stage="cold_"+name,fixture=fx["id"],prompt_sha256=fx["prompt_sha256"],**gold))
        async def sweep(label, offsets, arms, repetitions, gate):
            for epoch in range(-1,repetitions):
                shift=(epoch+block)%len(offsets)
                order=list(offsets[shift:])+list(offsets[:shift])
                if (epoch+block)%2: order.reverse()
                for ms in order:
                    pair=list(arms)
                    if (epoch+block+OFFSETS.index(ms))%2: pair.reverse()
                    for arm in pair:
                        await r.probe(label,ms,arm,epoch,gate)
                print(length,label,epoch,flush=True)
        def collected(label):
            return [v for line in (dest/"rows.jsonl").read_text().splitlines()
                    if (v:=json.loads(line))["cell"]==label]
        if stage=="screen":
            await sweep("map",OFFSETS,("full","local"),6,2048)
            choice=choose(collected("map"))
            (dest/"choice.json").write_text(json.dumps(choice,indent=2))
            if choice["candidates"]:
                await sweep("verify",choice["candidates"],("full","local"),6,2048)
            verdict=verify(choice,collected("verify"))
            (dest/"verdict.json").write_text(json.dumps(verdict,indent=2))
        else:
            choice=json.loads(Path(selection).read_text())
            await sweep("confirm",choice["eligible"],("peer","gate"),8,
                        2048 if choice["gate"]=="full" else 2176)
if __name__=="__main__":
    asyncio.run(main(Path(sys.argv[1]),int(sys.argv[2]),sys.argv[3],int(sys.argv[4]),*sys.argv[5:]))
