"""Qualify cache actions and run counterbalanced single-request measurements."""

import argparse
import asyncio
import hashlib
import itertools
import json
from pathlib import Path
import random
import runpy
import statistics
import time
import uuid

import aiohttp
from prometheus_client.parser import text_string_to_metric_families
from swe_prefix_reuse.client import request, token_digest


ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:34762"
MODEL = "Qwen2.5-7B-Instruct"
B = 128
ELIGIBLE = 4 * B
CUT = 2 * B
TOKENS = 32
ACTIONS = {"full_reuse": ELIGIBLE, "partial_reuse": CUT, "recompute": 0}


def freeze_prompt():
    from transformers import AutoTokenizer

    original_tokens, trajectory, turn = runpy.run_path(
        str(ROOT / "measure-actions.py")
    )["freeze_prompt"]()
    original = AutoTokenizer.from_pretrained("/models/Qwen3.5-35B-A3B", local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained("/models/Qwen2.5-7B-Instruct", local_files_only=True)
    text = original.decode(original_tokens,
                           skip_special_tokens=False, clean_up_tokenization_spaces=False)
    prompt = tokenizer.encode(text, add_special_tokens=False)
    assert ELIGIBLE + B < len(prompt) < 16352
    return prompt, trajectory, turn


class ForcedHTTP:
    def __init__(self, session, action, reuse, req_id):
        self.session = session
        self.action = action
        self.reuse = reuse
        self.req_id = req_id

    def post(self, url, *, json, headers):
        return self.session.post(
            url,
            json={**json, "request_id": self.req_id},
            headers={
                **headers,
                "x-request-id": self.req_id,
                "x-bench-kv-action": self.action,
                "x-bench-kv-reuse": str(self.reuse),
                "x-bench-kv-eligible": str(ELIGIBLE if self.reuse else 0),
            },
        )


async def metrics(http):
    async with http.get(BASE + "/metrics") as response:
        response.raise_for_status()
        return {
            (sample.name, tuple(sorted(sample.labels.items()))): sample.value
            for family in text_string_to_metric_families(await response.text())
            for sample in family.samples
        }


def stats(before, after):
    def delta(name, **labels):
        return sum(value - before.get((key, tags), 0.0)
                   for (key, tags), value in after.items()
                   if key == f"vllm:{name}" and labels.items() <= dict(tags).items())
    return {
        "prefill_s": delta("request_prefill_time_seconds_sum"),
        "queue_s": delta("request_queue_time_seconds_sum"),
        "decode_s": delta("request_decode_time_seconds_sum"),
        "local_cache": delta("prompt_tokens_by_source_total", source="local_cache_hit"),
        "external_cache": delta("prompt_tokens_by_source_total", source="external_kv_transfer"),
        "computed": delta("prompt_tokens_by_source_total", source="local_compute"),
    }


class Experiment:
    def __init__(self, http, directory, prompt, connector=False):
        self.http = http
        self.directory = directory
        self.prompt = prompt
        self.connector = connector
        engine_path = directory / "engine.jsonl"
        engine_path.touch(exist_ok=True)
        self.engine = engine_path.open()

    def offload_since(self, timestamp):
        return [row for file in sorted(self.directory.glob("offload-*.jsonl"))
                for line in file.read_text().splitlines() if line.endswith("}")
                and (row := json.loads(line))["timestamp_ns"] >= timestamp]

    async def reset(self, external=False):
        path = self.directory / "server.log"
        for _ in range(40):
            start = time.time_ns()
            with path.open() as log:
                log.seek(0, 2)
                async with self.http.post(
                    BASE + "/reset_prefix_cache", params={"reset_external": str(external).lower()}
                ) as response:
                    response.raise_for_status()
                local = "Successfully reset prefix cache" in log.read()
            remote = not external or any(
                row["kind"] == "reset_external" and row["success"]
                for row in self.offload_since(start)
            )
            if local and remote:
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("cache reset was not confirmed by the engine")

    async def run(self, action, prompt, anchor, budget, *, stage, expected,
                  cut=None, measure=False, external=0):
        reuse = ACTIONS[action] if cut is None else cut
        # Seed shorter prompts with the normal anchor namespace and a zero
        # eligible-prefix declaration. No hits are expected in a new anchor.
        req_id = f"kv41-{stage}-{uuid.uuid4().hex[:12]}"
        transport = ForcedHTTP(self.http, action, reuse, req_id)
        before = await metrics(self.http) if measure else None
        start = time.time_ns()
        output = await request(transport, BASE + "/v1/completions", MODEL, prompt, budget,
                               anchor, 17)
        assert output.success, (req_id, output.error)
        observed = []
        for line in self.engine:
            row = json.loads(line)
            if row["request_id"].startswith(f"cmpl-{req_id}-"):
                observed.append(row)
        lookups = [row for row in observed if row["event"] == "lookup"]
        assert lookups, (req_id, observed)
        first = lookups[0]
        assert first["hash_block_size"] == B and first["applied_decision"] == action, first
        assert first["engine_reused_tokens"] == expected, (req_id, expected, first)
        assert first["engine_recomputed_tokens"] == len(prompt) - expected, first
        commits = [row for row in observed if row["event"] == "commit"]
        assert commits, req_id
        boundary = max(row["cacheable_boundary_tokens"] for row in commits)
        if action == "partial_reuse":
            assert boundary == reuse, (req_id, boundary, reuse)
        record = {
            "request_id": req_id,
            "stage": stage,
            "action": action,
            "anchor": anchor,
            "prompt_sha256": token_digest(prompt),
            "lookup": first,
            "cacheable_boundary_tokens": boundary,
            "ttft_ms": (output.first_token - output.start) * 1000,
            "tpot_ms": (output.last_token - output.first_token) * 1000 / max(1, budget - 1),
            "output_sha256": token_digest(output.token_ids),
            "output_ids": output.token_ids,
        }
        if measure:
            record["server"] = stats(before, await metrics(self.http))
            assert record["server"]["local_cache"] == expected, record
            assert record["server"]["external_cache"] == external, record
            assert record["server"]["computed"] == len(prompt) - expected - external, record
            if self.connector:
                receipts = self.offload_since(start)
                matches = [row for row in receipts if row["kind"] == "lookup"
                           and row["request_id"].startswith(f"cmpl-{req_id}-")]
                assert matches and matches[0]["external_tokens"] == external, matches
                read = [row for row in receipts if row["kind"] == "load"]
                assert bool(read) == bool(external), (external, receipts)
                record["offload"] = read
        with (self.directory / "measurements.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        return record

    async def pair_arm(self, action, stage, staged=False):
        await self.reset(external=self.connector)
        anchor = f"{stage}-{uuid.uuid4().hex}"
        await self.run("full_reuse", self.prompt[:CUT + 1], anchor, 16,
                       stage="seed-cut", expected=0, cut=0)
        await self.run("full_reuse", self.prompt[:ELIGIBLE + 1], anchor, 16 if self.connector else 1,
                       stage="seed-full", expected=CUT, cut=0)
        if staged:
            await self.reset()
        return await self.run(action, self.prompt, anchor, TOKENS, stage=stage,
                              expected=0 if staged else ACTIONS[action],
                              external=ACTIONS[action] if staged else 0, measure=True)

    async def isolate(self):
        await self.reset(external=self.connector)
        anchor = f"tail-isolation-{uuid.uuid4().hex}"
        await self.run("full_reuse", self.prompt[:CUT + 1], anchor, 1,
                       stage="isolation-seed", expected=0, cut=0)
        partial = await self.run("partial_reuse", self.prompt, anchor, TOKENS,
                       stage="isolation-partial", expected=CUT)
        probe = await self.run("full_reuse", self.prompt, anchor, TOKENS,
                               stage="isolation-probe", expected=CUT, measure=True)
        return partial, probe


def report(blocks):
    means = {
        a: {"ttft_ms": statistics.mean(b[a]["ttft_ms"] for b in blocks),
            "tpot_ms": statistics.mean(b[a]["tpot_ms"] for b in blocks)}
        for a in ACTIONS
    }
    comparisons = {}
    for left, right in itertools.combinations(ACTIONS, 2):
        deltas = [b[left]["ttft_ms"] - b[right]["ttft_ms"] for b in blocks]
        center = statistics.mean(deltas)
        # Student t(5), two-sided 95% interval across the six paired blocks.
        margin = 2.570582 * statistics.stdev(deltas) / len(deltas) ** .5
        comparisons[f"{left}-minus-{right}"] = {
            "mean_ms": center, "ci95_ms": [center - margin, center + margin],
            "paired_ms": deltas,
        }
    return {"means": means, "ttft_differences": comparisons, "blocks": blocks}


async def main(directory, connector):
    label = str(ELIGIBLE)
    prompt, trajectory, turn = freeze_prompt()
    receipt = {
        "prepared_sha256": hashlib.sha256((ROOT / "prepared.json").read_bytes()).hexdigest(),
        "prompt_sha256": token_digest(prompt), "trajectory": trajectory, "turn": turn,
        "prompt_tokens": len(prompt), "output_tokens": TOKENS,
        "block_tokens": B, "resident_prefix_tokens": ELIGIBLE, "partial_cut_tokens": CUT,
        "seed_method": "materialize cut checkpoint first, then extend the same namespace",
        "tokenizer": MODEL, "prompt_method": "decode verified Open-SWE turn with actual continuation and retokenize",
    }
    (directory / f"fixture-{label}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=240)) as http:
        local = Experiment(http, directory, prompt, connector)
        orders = list(itertools.permutations(ACTIONS))
        random.Random(4101).shuffle(orders)
        regimes = ("resident", "staged") if connector else ("resident",)
        for regime in regimes:
            staged = regime == "staged"
            qualification = [await local.pair_arm(a, f"{label}-{regime}-qualification", staged) for a in ACTIONS]
            print(f"Qualified {regime} actions:", [
                (r["action"], r["server"]["local_cache"], r["server"]["external_cache"], r["output_sha256"])
                for r in qualification
            ], flush=True)
            if not staged:
                partial, probe = await local.isolate()
                print("Tail-isolation probe passed", flush=True)
                reference = qualification[-1]["output_sha256"]
                print("Cut-only reference check:", {
                    "partial_matches": partial["output_sha256"] == reference,
                    "native_matches": probe["output_sha256"] == reference,
                }, flush=True)
                assert probe["output_sha256"] == reference, "native cut-only checkpoint differs"
            assert len({r["output_sha256"] for r in qualification}) == 1, "reference output mismatch"
            data = []
            for index, order in enumerate(orders):
                block = {a: await local.pair_arm(a, f"{label}-{regime}-block{index}", staged) for a in order}
                assert len({r["output_sha256"] for r in block.values()}) == 1, (index, "reference mismatch")
                data.append(block)
                print(f"completed {regime} block {index + 1}/{len(orders)}", flush=True)
            result = report(data)
            (directory / f"{label}-{regime}-summary.json").write_text(json.dumps(result, indent=2) + "\n")
            print(result["means"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--connector", action="store_true")
    parser.add_argument("--prefix", required=True, type=int, choices=(1024, 2048, 3072, 4096))
    args = parser.parse_args()
    ELIGIBLE = args.prefix
    CUT = ELIGIBLE // 2
    ACTIONS = {"full_reuse": ELIGIBLE, "partial_reuse": CUT, "recompute": 0}
    asyncio.run(main(args.directory, args.connector))
