"""Paired, exact-output qualification and timing for the #41 LMCache sweep."""

import asyncio
import json
from pathlib import Path
import random
import re
import runpy
import statistics
import sys
import time
import uuid

import aiohttp


BASE_DIR = Path(__file__).resolve().parent
HELPERS = runpy.run_path(str(BASE_DIR / "measure-sota-long-sweep.py"))
BASE = HELPERS["BASE"]
MODEL = HELPERS["MODEL"]
P = 10449
PROBE = 4096
LOCAL = 2048
B = 128
BUDGET = 32
ACTIONS = ("full", "cut3584", "cut3072", "cut2048", "recompute", "threshold")
MODES = ("idle", "high")
RECEIPT = re.compile(r"Retrieved (\d+) tokens in ([\d.]+) seconds")


class Tagged:
    def __init__(self, http, salt, opts):
        self.http = http
        self.salt = salt
        self.opts = opts

    def post(self, url, **kwargs):
        body = kwargs["json"]
        body["cache_salt"] = self.salt
        body["kv_transfer_params"] = self.opts
        return self.http.post(url, **kwargs)


class Run:
    def __init__(self, http, dest, prompt):
        self.http = http
        self.dest = dest
        self.prompt = prompt
        self.salt = uuid.uuid4().hex
        self.traffic_counter = 0

    def record(self, filename, row):
        with (self.dest/filename).open("a") as f:
            f.write(json.dumps(row) + "\n")

    def receipts(self, event, tag):
        rows = []
        for f in self.dest.glob("connector-*.jsonl"):
            for line in f.read_text().splitlines():
                if not line.endswith("}"):
                    continue
                row = json.loads(line)
                if row["event"] == event and row.get("tag") == tag:
                    rows.append(row)
        return rows

    async def traffic(self, mode):
        self.traffic_counter += 1
        tag = f"step-{self.traffic_counter:04d}"
        temp = self.dest/"traffic-next"
        temp.write_text(f"{tag} {mode}\n")
        temp.replace(self.dest/"traffic")
        for _ in range(125):
            workers = {r["device"] for r in self.receipts("copy_ack", tag)}
            if len(workers) == 2:
                return tag
            await asyncio.sleep(0.04)
        raise RuntimeError(f"Did not get two copy-lane acknowledgements for {tag} {mode}")

    async def reset_local(self):
        log = self.dest/"engine.log"
        for _ in range(30):
            with log.open() as f:
                f.seek(0, 2)
                async with self.http.post(BASE + "/reset_prefix_cache") as response:
                    response.raise_for_status()
                if "Successfully reset prefix cache" in f.read():
                    return
            await asyncio.sleep(0.1)
        raise RuntimeError("Local cache reset not confirmed")

    async def sample(self, salt, tokens, budget, opts):
        before = await HELPERS["metrics"](self.http)
        t0 = time.time_ns()
        response = await HELPERS["request"](Tagged(self.http, salt, opts),
                                            BASE + "/v1/completions", MODEL, tokens,
                                            budget, salt, 17)
        assert response.success, response.error
        t1 = t0 + int(1e9 * (response.first_token-response.start))
        counts = HELPERS["stats"](before, await HELPERS["metrics"](self.http))
        return {"start_ns": t0, "first_token_ns": t1, "counts": counts,
                "ttft_ms": (response.first_token-response.start)*1000,
                "tpot_ms": (response.last_token-response.first_token)*1000 / max(1, budget-1),
                "output_ids": response.token_ids,
                "output_sha256": HELPERS["token_digest"](response.token_ids)}

    async def seed(self):
        seed = await self.sample(self.salt, self.prompt[:PROBE+1], 1, {})
        assert seed["counts"]["computed"] == PROBE+1, seed
        # The coordinator logs the completed store across both ranks.
        for _ in range(75):
            if (self.dest/"cache.log").read_text().count("Stored 4096 tokens") >= 1:
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("LMCache did not confirm the 4096-token store")
        self.record("setup.jsonl", {"stage": "shared_seed", **seed})

    async def target(self, arm, mode, phase, threshold=2176):
        await self.reset_local()
        prime = await self.sample(self.salt, self.prompt[:LOCAL+1], 1, {
            "lmcache.kv41_arm": str(LOCAL), "lmcache.max_offload_tokens": 0,
        })
        assert prime["counts"]["local_cache"] == 0, prime
        assert prime["counts"]["computed"] == 1 and prime["counts"]["external_cache"] == LOCAL, prime
        self.record("setup.jsonl", {"stage": "resident_prime", "phase": phase, **prime})
        expected = {"full": PROBE, "recompute": 0,
                    "threshold": PROBE if threshold <= PROBE-LOCAL else LOCAL}.get(arm)
        if expected is None:
            expected = int(arm.removeprefix("cut"))
        salt = self.salt if arm != "recompute" else self.salt + "-cold"
        opts = {"lmcache.kv41_arm": "threshold" if arm == "threshold" else str(expected),
                "lmcache.kv41_min_external": threshold, "lmcache.max_offload_tokens": 0}
        cache_log = self.dest/"cache.log"
        with cache_log.open() as f:
            f.seek(0, 2)
            tag = await self.traffic(mode)
            try:
                row = await self.sample(salt, self.prompt, BUDGET, opts)
            finally:
                await self.traffic("idle")
            transfers = [[int(tokens), float(seconds)*1000] for tokens, seconds in RECEIPT.findall(f.read())]
        actual_local = 0 if arm == "recompute" else LOCAL
        actual_external = expected - actual_local
        counts = row["counts"]
        copy_batches = self.receipts("copy_batch", tag)
        overlapped = [b for b in copy_batches if b["begin_ns"] < row["first_token_ns"]
                      and b["end_ns"] > row["start_ns"]]
        copy_bytes = {d: sum(b["bytes"] for b in overlapped if b["device"] == d)
                      for d in sorted({b["device"] for b in overlapped})}
        row.update(arm=arm, mode=mode, phase=phase, threshold=threshold, tag=tag,
                   expected_local=actual_local, expected_external=actual_external,
                   background_overlap_bytes=copy_bytes, retrieved=transfers)
        self.record("targets.jsonl", row)
        assert counts["local_cache"] == actual_local, row
        assert counts["external_cache"] == actual_external, row
        assert counts["computed"] == P-expected, row
        # LMCache's coordinator logs total tokens after receiving both workers.
        assert [tokens for tokens, _ in transfers] == ([actual_external] if actual_external else []), row
        assert (len(copy_bytes) == 2 if mode == "high" else not copy_bytes), row
        assert len(row["output_ids"]) == BUDGET, row
        return row


def paired_summary(evaluated, arms):
    ans = {}
    for mode in MODES:
        rounds = evaluated[mode]
        means = {a:statistics.mean(r[a]["ttft_ms"] for r in rounds) for a in arms}
        comparisons = {}
        for a in arms:
            for b in arms:
                if a == b:
                    continue
                d = [r[a]["ttft_ms"] - r[b]["ttft_ms"] for r in rounds]
                center = statistics.mean(d)
                width = 2.570582 * statistics.stdev(d) / len(d)**0.5
                comparisons[f"{a}-minus-{b}"] = {"mean_ms":center, "ci95_ms":[center-width,center+width], "paired_ms":d}
        best = min((a for a in arms if a != "threshold"), key=means.get)
        winner = best if all(means[best] <= means[b]*0.95
                             and comparisons[f"{best}-minus-{b}"]["ci95_ms"][1] < 0
                             for b in arms if b != best and not (
                                 b == "threshold" and best == ("full" if rounds[0]["threshold"]["threshold"] <= 2048
                                                              else "cut2048"))) else None
        binary = min(("full","cut2048"), key=means.get)
        ans[mode] = {"means": means, "best": best, "qualified_winner": winner,
                     "best_tier_aware_endpoint":binary,
                     "best_tier_aware_endpoint_headroom_ms": means[binary]-min(means[a] for a in arms if a!="threshold"),
                     "comparisons":comparisons, "blocks":rounds}
    return ans


async def main(dest):
    prompt, trajectory, turn = HELPERS["freeze_prompt"]()
    assert len(prompt) == P
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as http:
        trial = Run(http,dest,prompt)
        await trial.traffic("idle")
        await trial.seed()
        reference = await trial.target("recompute","idle","reference")
        expected = reference["output_ids"]
        good = {}
        qualification = {}
        for mode in MODES:
            good[mode] = set()
            qualification[mode] = {}
            for a in ACTIONS[:-1]:
                row = await trial.target(a,mode,"qualification")
                same = row["output_ids"] == expected
                qualification[mode][a] = same
                if same:
                    good[mode].add(a)
                print("qualification",mode,a,same,row["counts"]["local_cache"],
                      row["counts"]["external_cache"],row["retrieved"],flush=True)
        jointly_good = good["idle"] & good["high"]
        assert {"full","cut2048","recompute"} <= jointly_good, qualification
        # Calibrate the independent, two-action external-token gate on two fresh
        # paired endpoints per regime; never fit on a timed pair.
        threshold = {}
        for mode in MODES:
            cost = {a:[] for a in ("full","cut2048")}
            for order in (("full","cut2048"),("cut2048","full")):
                for a in order:
                    row = await trial.target(a,mode,"calibration")
                    assert row["output_ids"] == expected
                    cost[a].append(row["ttft_ms"])
            threshold[mode] = 2048 if statistics.mean(cost["full"]) < statistics.mean(cost["cut2048"]) else 2176
            row = await trial.target("threshold",mode,"qualification",threshold[mode])
            assert row["output_ids"] == expected
        full_probe = {m: [(r["ttft_ms"],r["retrieved"]) for line in (dest/"targets.jsonl").open()
                          if (r:=json.loads(line))["mode"]==m and r["arm"]=="full"
                          and r["phase"] in ("qualification","calibration")] for m in MODES}
        print("threshold",threshold,"probe",full_probe,flush=True)
        arms = [a for a in ACTIONS if a in jointly_good or a == "threshold"]
        info = {"prompt_sha256":HELPERS["token_digest"](prompt),"reference_sha256":reference["output_sha256"],
                "trajectory":trajectory,"turn":turn,"threshold":threshold,"qualification":qualification,
                "arms":arms,"full_probe":full_probe}
        (dest/"qualification.json").write_text(json.dumps(info,indent=2)+"\n")
        # Refuse to interpret a stress test if it did not measurably change
        # LMCache's retrieval time on the common full-load operation.
        ratios = {m:statistics.median(e[1][0][1] for e in full_probe[m]) for m in MODES}
        print("median full retrieval, ms",ratios,flush=True)
        phase="timed" if ratios["high"] >= ratios["idle"]*1.10 else "timed_unverified_contention"
        evaluated = {m:[] for m in MODES}
        order = arms.copy()
        random.Random(414096).shuffle(order)
        for n in range(6):
            for mode in MODES[::1 if n%2==0 else -1]:
                shift = n % len(order)
                ordered = order[shift:]+order[:shift]
                block = {}
                for a in ordered:
                    row = await trial.target(a,mode,phase,threshold[mode])
                    assert row["output_ids"] == expected, (mode,a,n)
                    block[a] = row
                evaluated[mode].append(block)
                print("completed",mode,n+1,flush=True)
        info.update(phase=phase, median_qualification_full_retrieval_ms=ratios,
                    results=paired_summary(evaluated,arms))
        (dest/"contention-summary.json").write_text(json.dumps(info,indent=2)+"\n")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
