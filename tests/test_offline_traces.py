from __future__ import annotations

from vllm_kv_materialization.offline_traces import (
	build_signals,
	workload_case_to_traces,
)


def test_workload_case_to_traces_emits_shared_workload_driven_rows() -> None:
	traces = workload_case_to_traces("shared_scenario_multi_turn_knowledge_service", seed=7)

	assert traces
	assert traces[0]["workload_case"] == "shared_scenario_multi_turn_knowledge_service"
	assert traces[0]["reusable_prefix_tokens"] >= 0
	assert 0.0 <= traces[0]["queue_pressure"] <= 0.95


def test_build_signals_round_trips_offline_trace_fields() -> None:
	raw = {
		"reusable_prefix_tokens": 768,
		"remote_kv_bytes": 768 * 32768,
		"transfer_time_ms": 7.5,
		"recompute_time_ms": 13.0,
		"queue_pressure": 0.42,
		"ttft_sensitive": True,
		"reuse_confidence": 0.73,
	}

	signals = build_signals(raw)

	assert signals.reusable_prefix_tokens == 768
	assert signals.remote_kv_bytes == 768 * 32768
	assert signals.transfer_time_ms == 7.5
	assert signals.queue_pressure == 0.42
	assert signals.reuse_confidence == 0.73