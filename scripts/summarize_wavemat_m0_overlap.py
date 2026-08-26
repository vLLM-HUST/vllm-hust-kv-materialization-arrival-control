#!/usr/bin/env python3
"""Fail-closed summarizer for the WaveMat M0 layer-ready trace.

The upstream observation point is the *actual* AscendStore consumer wait:
``KVPoolWorker.wait_for_layer_load``.  A patched, disposable upstream checkout
emits ``WAVEMAT_TIMING layer=<n> load_wait_s=<seconds>`` at that point.  This
tool deliberately refuses to infer transfer/compute overlap from wall-clock
time: without layer-ready records it writes no favourable conclusion.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path


WAIT_RE = re.compile(r"WAVEMAT_TIMING\s+layer=(?P<layer>\d+)\s+load_wait_s=(?P<wait>[0-9.]+)")


def percentile(values: list[float], percentile: float) -> float:
    return round(
        statistics.quantiles(values, n=100, method="inclusive")[percentile - 1], 6
    )


def read_waits(path: Path) -> dict[int, list[float]]:
    by_layer: dict[int, list[float]] = {}
    for match in WAIT_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
        by_layer.setdefault(int(match["layer"]), []).append(float(match["wait"]))
    return by_layer


def summarize(path: Path, bubble_threshold_s: float) -> dict[str, object]:
    by_layer = read_waits(path)
    values = [value for layer_values in by_layer.values() for value in layer_values]
    if not values:
        raise ValueError(f"no WAVEMAT_TIMING layer-ready waits found in {path}")
    per_layer = {
        str(layer): {
            "samples": len(layer_values),
            "wait_s_mean": round(statistics.fmean(layer_values), 6),
            "wait_s_p95": percentile(layer_values, 95) if len(layer_values) > 1 else round(layer_values[0], 6),
            "bubble_samples": sum(value >= bubble_threshold_s for value in layer_values),
        }
        for layer, layer_values in sorted(by_layer.items())
    }
    return {
        "trace": str(path),
        "samples": len(values),
        "layers": len(by_layer),
        "load_wait_s_mean": round(statistics.fmean(values), 6),
        "load_wait_s_p50": percentile(values, 50),
        "load_wait_s_p95": percentile(values, 95),
        "load_wait_s_total": round(sum(values), 6),
        "bubble_threshold_s": bubble_threshold_s,
        "bubble_samples": sum(value >= bubble_threshold_s for value in values),
        "per_layer": per_layer,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize M0 real layer-ready waits.")
    parser.add_argument("--graph-log", type=Path, required=True)
    parser.add_argument("--eager-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bubble-threshold-ms", type=float, default=0.1)
    args = parser.parse_args()
    threshold_s = args.bubble_threshold_ms / 1000
    graph = summarize(args.graph_log, threshold_s)
    eager = summarize(args.eager_log, threshold_s)
    delta = float(graph["load_wait_s_mean"]) - float(eager["load_wait_s_mean"])
    result = {
        "artifact": "m0-wavemat-layer-ready-wait-summary",
        "is_wavemat_mechanism_enabled": False,
        "graph": graph,
        "eager": eager,
        "graph_minus_eager_load_wait_s_mean": round(delta, 6),
        "overlap_ratio": None,
        "gate_interpretation": (
            "Layer-ready wait is measured at the real Ascend consumer seam. "
            "This artifact alone does not establish transfer-compute overlap; "
            "a device-event timeline is required before claiming sufficient overlap."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
