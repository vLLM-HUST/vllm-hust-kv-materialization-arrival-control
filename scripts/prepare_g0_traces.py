#!/usr/bin/env python3
"""Prepare pinned BurstGPT and ServeGen arrival carriers for G0.

Only arrival shape comes from the public sources. Prompt token IDs are a
deterministic, auditable reuse overlay with 128/256/384-token shared prefixes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

PREFIX_TOKENS = (128, 256, 384)
SUFFIX_TOKENS = 32
OUTPUT_TOKENS = 8
BYTES_PER_REUSED_TOKEN = 27 * (512 + 64) * 2  # V2-Lite MLA, bf16, TP=1.


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def busiest_positive_span(timestamps: list[float], count: int) -> int:
    """Select the densest count-row window whose measured span is nonzero."""
    best: tuple[float, int] | None = None
    for start in range(len(timestamps) - count + 1):
        span = timestamps[start + count - 1] - timestamps[start]
        if span <= 0:
            continue
        candidate = (span, start)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise ValueError("source has no positive-span request window")
    return best[1]


def burstgpt_arrivals(csv_path: Path, count: int) -> tuple[list[float], dict[str, Any]]:
    timestamps: list[float] = []
    with csv_path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            timestamps.append(float(row["Timestamp"]))
    start = busiest_positive_span(timestamps, count)
    selected = timestamps[start : start + count]
    relative = [value - selected[0] for value in selected]
    return relative, {
        "format": "BurstGPT_1.csv",
        "source_row_start": start,
        "source_row_end_exclusive": start + count,
        "source_timestamp_start": selected[0],
        "source_timestamp_end": selected[-1],
    }


def servegen_arrivals(root: Path, count: int, seed: int) -> tuple[list[float], dict[str, Any]]:
    # Client 38, window 0 is pinned before measurement: CV=20.0796 and uses
    # ServeGen's fitted Weibull arrival process. Call the upstream sampler
    # directly so this remains a ServeGen trace, not a local approximation.
    sys.path.insert(0, str(root))
    from servegen.construct import _sample_iats  # type: ignore
    from servegen.workload_types import ClientWindow  # type: ignore

    trace_path = root / "data/language/m-small/chunk-38-trace.csv"
    with trace_path.open(newline="", encoding="utf-8") as source:
        first = next(csv.reader(source))
    timestamp, rate, cv, pattern, shape, scale = first
    window = ClientWindow(
        client_id=38,
        timestamp=int(timestamp),
        window_size=600,
        rate=float(rate),
        cv=float(cv),
        arrival_pat=(pattern, (float(shape), float(scale))),
        dataset=None,
    )
    iats = _sample_iats(window, float(rate), np.random.RandomState(seed))
    arrivals = np.cumsum(iats[:count])
    arrivals -= arrivals[0]
    return arrivals.tolist(), {
        "format": "ServeGen language/m-small client 38 window 0",
        "client_id": 38,
        "window_timestamp": int(timestamp),
        "rate": float(rate),
        "cv": float(cv),
        "arrival_pattern": [pattern, [float(shape), float(scale)]],
        "seed": seed,
    }


def normalize_one_rps(arrivals: list[float]) -> list[float]:
    span = arrivals[-1] - arrivals[0]
    if span <= 0:
        raise ValueError("arrival carrier must have positive duration")
    target_span = len(arrivals) - 1
    return [(value - arrivals[0]) * target_span / span for value in arrivals]


def token_pattern(model: Path) -> list[int]:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    ids = tokenizer.encode(
        " materialization reuse carrier alpha beta gamma delta epsilon zeta eta theta",
        add_special_tokens=False,
    )
    special = set(tokenizer.all_special_ids)
    ids = [token for token in ids if token not in special]
    if len(ids) < 4:
        raise ValueError("tokenizer did not produce a usable carrier pattern")
    return ids


def repeat_to(pattern: list[int], length: int, offset: int) -> list[int]:
    return [pattern[(offset + index) % len(pattern)] for index in range(length)]


def write_trace(
    path: Path,
    workload: str,
    arrivals: list[float],
    pattern: list[int],
) -> None:
    prefixes = {
        length: repeat_to(pattern, length, group * 3)
        for group, length in enumerate(PREFIX_TOKENS)
    }
    with path.open("w", encoding="utf-8") as destination:
        for index, arrival in enumerate(normalize_one_rps(arrivals)):
            prefix_len = PREFIX_TOKENS[index % len(PREFIX_TOKENS)]
            suffix = repeat_to(pattern, SUFFIX_TOKENS, index + 11)
            row = {
                "request_id": f"g0-{workload}-{index:04d}",
                "arrival_s": arrival,
                "prompt_token_ids": prefixes[prefix_len] + suffix,
                "prefix_token_ids": prefixes[prefix_len],
                "reuse_prefix_tokens": prefix_len,
                "output_tokens": OUTPUT_TOKENS,
                "target_materialization_bytes": prefix_len * BYTES_PER_REUSED_TOKEN,
                "source_sequence_index": index,
            }
            destination.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--burstgpt-root", default="/root/BurstGPT")
    parser.add_argument("--servegen-root", default="/root/ServeGen")
    parser.add_argument("--model", default="/root/models/DeepSeek-V2-Lite")
    parser.add_argument("--requests", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260831)
    args = parser.parse_args()

    output = Path(args.output_dir).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite trace directory: {output}")
    output.mkdir(parents=True)
    burst_root, serve_root = Path(args.burstgpt_root), Path(args.servegen_root)
    burst_csv = burst_root / "data/BurstGPT_1.csv"
    burst, burst_selection = burstgpt_arrivals(burst_csv, args.requests)
    serve, serve_selection = servegen_arrivals(serve_root, args.requests, args.seed)
    pattern = token_pattern(Path(args.model))
    outputs = {}
    for workload, arrivals in (("burstgpt", burst), ("servegen", serve)):
        trace = output / f"{workload}_base.jsonl"
        write_trace(trace, workload, arrivals, pattern)
        outputs[workload] = {
            "path": str(trace),
            "bytes": trace.stat().st_size,
            "sha256": sha256(trace),
            "requests": args.requests,
        }
    write_json(
        output / "source_manifest.json",
        {
            "schema_version": 1,
            "overlay": {
                "prefix_tokens": list(PREFIX_TOKENS),
                "suffix_tokens": SUFFIX_TOKENS,
                "output_tokens": OUTPUT_TOKENS,
                "bytes_per_reused_token": BYTES_PER_REUSED_TOKEN,
                "base_mean_rps": 1.0,
            },
            "burstgpt": {
                "commit": git_commit(burst_root),
                "source_path": str(burst_csv.resolve()),
                "source_bytes": burst_csv.stat().st_size,
                "source_sha256": sha256(burst_csv),
                "selection": burst_selection,
            },
            "servegen": {
                "commit": git_commit(serve_root),
                "source_path": str(
                    (serve_root / "data/language/m-small/chunk-38-trace.csv").resolve()
                ),
                "source_sha256": sha256(
                    serve_root / "data/language/m-small/chunk-38-trace.csv"
                ),
                "selection": serve_selection,
            },
            "outputs": outputs,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
