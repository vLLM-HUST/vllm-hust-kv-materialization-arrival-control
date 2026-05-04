from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vllm_kv_materialization.policy import MaterializationSignals
from vllm_kv_materialization.shared_workloads import generate_case_requests
from vllm_kv_materialization.shared_workloads import load_workloads_module


WORKLOADS = load_workloads_module()

TTFT_SENSITIVE_FAMILIES = {
	"session-affine-multi-turn",
	"session-affine-bursty",
	"rag-followup",
	"tool-scaffold-agent",
	"repo-aware-coding-assistant",
	"realtime-voice-assistant",
}

TRANSFER_FACTOR_MS_BY_FAMILY = {
	"session-affine-multi-turn": 0.0048,
	"session-affine-bursty": 0.0046,
	"rag-followup": 0.0064,
	"long-context-doc-analysis": 0.0072,
	"tool-scaffold-agent": 0.0056,
	"repo-aware-coding-assistant": 0.0061,
}

RECOMPUTE_FACTOR_MS_BY_FAMILY = {
	"session-affine-multi-turn": 0.0110,
	"session-affine-bursty": 0.0108,
	"rag-followup": 0.0118,
	"long-context-doc-analysis": 0.0132,
	"tool-scaffold-agent": 0.0114,
	"repo-aware-coding-assistant": 0.0121,
}


def load_traces(path: Path) -> list[dict[str, Any]]:
	traces: list[dict[str, Any]] = []
	for line in path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line:
			continue
		traces.append(json.loads(line))
	return traces


def workload_case_to_traces(case_id: str, *, seed: int) -> list[dict[str, Any]]:
	if case_id not in WORKLOADS.SHARED_BENCHMARK_CASE_CATALOG:
		raise ValueError(f"unknown workload case: {case_id}")

	requests = generate_case_requests(case_id, seed=seed)
	traces: list[dict[str, Any]] = []
	seen_primary: set[str] = set()
	seen_secondary: set[str] = set()
	rank_counts: dict[int, int] = {}

	for index, request in enumerate(requests):
		metadata = WORKLOADS.normalize_repo_local_metadata(request.repo_local_metadata)
		secondary_seen = len(set(metadata.secondary_anchor_ids) & seen_secondary)
		secondary_total = max(len(metadata.secondary_anchor_ids), 1)
		overlap_ratio = secondary_seen / secondary_total
		primary_seen = metadata.primary_anchor_id in seen_primary

		primary_ratio = 0.5 if primary_seen else 0.0
		overlap_bonus = 0.28 * overlap_ratio
		exact_turn_bonus = 0.06 if metadata.turn_index > 0 else 0.0
		reusable_ratio = min(0.88, primary_ratio + overlap_bonus + exact_turn_bonus)
		reusable_tokens = int(round(request.prompt_len * reusable_ratio))

		rank_count = rank_counts.get(metadata.home_rank, 0)
		queue_pressure = min(
			0.95,
			0.18 + (0.09 * rank_count) + (0.08 if primary_seen else 0.0) + (0.05 * secondary_seen),
		)

		reuse_confidence = min(0.98, 0.2 + (0.45 if primary_seen else 0.0) + (0.3 * overlap_ratio))
		transfer_factor_ms = TRANSFER_FACTOR_MS_BY_FAMILY.get(metadata.workload_family, 0.0055)
		recompute_factor_ms = RECOMPUTE_FACTOR_MS_BY_FAMILY.get(metadata.workload_family, 0.0116)
		confidence_penalty = 1.0 + max(0.0, 0.6 - reuse_confidence) * 2.8
		transfer_time_ms = 1.1 + (
			reusable_tokens
			* transfer_factor_ms
			* (1.0 + max(queue_pressure - 0.3, 0.0) * 0.75)
			* confidence_penalty
		)
		recompute_time_ms = (request.prompt_len * recompute_factor_ms) + (request.output_len * 0.01)
		recompute_time_ms *= 1.0 + (queue_pressure * 0.18)

		traces.append(
			{
				"trace_id": f"{case_id}-{index}",
				"workload_case": case_id,
				"workload_family": metadata.workload_family,
				"reusable_prefix_tokens": reusable_tokens,
				"remote_kv_bytes": reusable_tokens * 32768,
				"transfer_time_ms": round(transfer_time_ms, 3),
				"recompute_time_ms": round(recompute_time_ms, 3),
				"queue_pressure": round(queue_pressure, 3),
				"ttft_sensitive": metadata.workload_family in TTFT_SENSITIVE_FAMILIES,
				"reuse_confidence": round(reuse_confidence, 3),
				"prompt_len": int(request.prompt_len),
				"output_len": int(request.output_len),
			}
		)

		seen_primary.add(metadata.primary_anchor_id)
		seen_secondary.update(metadata.secondary_anchor_ids)
		rank_counts[metadata.home_rank] = rank_count + 1

	return traces


def build_signals(raw: dict[str, Any]) -> MaterializationSignals:
	return MaterializationSignals(
		reusable_prefix_tokens=int(raw["reusable_prefix_tokens"]),
		remote_kv_bytes=int(raw["remote_kv_bytes"]),
		transfer_time_ms=float(raw["transfer_time_ms"]),
		recompute_time_ms=float(raw["recompute_time_ms"]),
		queue_pressure=float(raw["queue_pressure"]),
		ttft_sensitive=bool(raw.get("ttft_sensitive", True)),
		reuse_confidence=float(raw.get("reuse_confidence", 0.0)),
	)


__all__ = ["build_signals", "load_traces", "workload_case_to_traces"]