from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def interval_union_overlap(
    start_us: float,
    end_us: float,
    compute_intervals: list[tuple[float, float]],
) -> float:
    """Return the unioned compute time inside a synchronous copy call."""
    overlaps = sorted(
        (max(start_us, start), min(end_us, end))
        for start, end in compute_intervals
        if start < end_us and end > start_us
    )
    total_us = 0.0
    right_edge = float("-inf")
    for start, end in overlaps:
        if end > right_edge:
            total_us += end - max(start, right_edge)
            right_edge = end
    return total_us


def summarize(trace: Path) -> dict[str, Any]:
    events = json.loads(trace.read_text(encoding="utf-8"))
    copies: list[tuple[float, float]] = []
    compute: list[tuple[float, float]] = []
    for event in events:
        try:
            start_us = float(event["ts"])
            end_us = start_us + float(event.get("dur", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if event.get("name") == "AscendCL@aclrtMemcpyBatch":
            copies.append((start_us, end_us))
        task_type = event.get("args", {}).get("Task Type", "")
        if task_type.startswith(("AI_", "MIX_")):
            compute.append((start_us, end_us))

    if not copies:
        raise ValueError("No AscendCL@aclrtMemcpyBatch events in trace")
    ratios = [
        interval_union_overlap(start, end, compute) / (end - start)
        for start, end in copies
        if end > start
    ]
    return {
        "metric": "synchronous_batch_copy_device_compute_overlap_proxy",
        "trace": str(trace),
        "copy_batches": len(copies),
        "npu_compute_tasks": len(compute),
        "batches_with_any_compute_overlap": sum(ratio > 0 for ratio in ratios),
        "batches_fully_covered_by_compute": sum(ratio >= 0.999 for ratio in ratios),
        "mean_overlap_ratio": round(statistics.mean(ratios), 6),
        "median_overlap_ratio": round(statistics.median(ratios), 6),
        "min_overlap_ratio": round(min(ratios), 6),
        "max_overlap_ratio": round(max(ratios), 6),
        "limitations": [
            "The trace labels aclrtMemcpyBatch as a synchronous copy call; this measures its wall interval against NPU AI-task intervals.",
            "It is a device-timeline proxy, not the final per-layer, gate-correlated WaveMat overlap ratio.",
            "Do not use this profiler-enabled workload wall clock for performance comparison.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize an Ascend M0 device timeline.")
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.trace)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
