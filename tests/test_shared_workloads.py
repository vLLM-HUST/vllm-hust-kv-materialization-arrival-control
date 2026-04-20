from __future__ import annotations

from vllm_kv_materialization.shared_workloads import build_live_workload
from vllm_kv_materialization.shared_workloads import DECISION_SURFACE_CASE_IDS
from vllm_kv_materialization.shared_workloads import DECISION_SURFACE_CASE_ROLES
from vllm_kv_materialization.shared_workloads import DEFAULT_LIVE_WORKLOAD_CASE
from vllm_kv_materialization.shared_workloads import EXPERIMENT_ARTICLE_CASE_IDS
from vllm_kv_materialization.shared_workloads import generate_case_requests
from vllm_kv_materialization.shared_workloads import load_workloads_module
from vllm_kv_materialization.shared_workloads import recommended_context_window


def test_default_experiment_cases_exist_in_shared_catalog() -> None:
	workloads = load_workloads_module()
	for case_id in EXPERIMENT_ARTICLE_CASE_IDS:
		assert case_id in workloads.SHARED_BENCHMARK_CASE_CATALOG
		assert case_id in DECISION_SURFACE_CASE_IDS
		assert case_id in DECISION_SURFACE_CASE_ROLES


def test_generate_case_requests_uses_shared_workload_cases() -> None:
	workloads = load_workloads_module()
	rows = generate_case_requests(DEFAULT_LIVE_WORKLOAD_CASE, seed=7)

	assert rows
	metadata = workloads.normalize_repo_local_metadata(rows[0].repo_local_metadata)
	assert metadata.workload_family == "session-affine-multi-turn"
	assert rows[0].prompt_len > 0
	assert rows[0].output_len > 0


def test_build_live_workload_preserves_shared_case_metadata() -> None:
	workload = build_live_workload(
		"shared_scenario_rag_followup_long_context",
		seed=7,
		request_rate=18,
		concurrency=3,
	)

	assert workload.case_id == "shared_scenario_rag_followup_long_context"
	assert workload.dataset_name == "rag-followup"
	assert workload.request_rate == 18
	assert workload.concurrency == 3
	assert workload.requests
	assert workload.requests[0].arrival_gap_s == 0.0
	assert workload.requests[1].arrival_gap_s > 0.0
	assert workload.requests[0].workload_family == "rag-followup"


def test_decision_surface_includes_new_state_management_cases() -> None:
	assert "shared_prefix_multi_tenant_assistant" in DECISION_SURFACE_CASE_IDS
	assert "session_continuation_with_maintenance" in DECISION_SURFACE_CASE_IDS
	assert "dynamic_rag_corpus_update" in DECISION_SURFACE_CASE_IDS


def test_generate_public_microbenchmark_case_requests() -> None:
	rows = generate_case_requests("shared_synthetic_shared_prefix_microbenchmark", seed=7)

	assert len(rows) == 32
	assert rows[0].prompt_len > 0
	assert rows[0].output_len == 64
	assert rows[0].repo_local_metadata["workload_family"] == "synthetic-shared-prefix"


def test_generate_public_sharegpt_boundary_case_requests() -> None:
	rows = generate_case_requests("shared_public_sharegpt_boundary", seed=7)

	assert len(rows) == 32
	assert rows[0].prompt_len > 0
	assert rows[0].repo_local_metadata["workload_family"] == "sharegpt-public-boundary"


def test_recommended_context_window_comes_from_shared_catalog() -> None:
	assert recommended_context_window(DEFAULT_LIVE_WORKLOAD_CASE) == 32768
	assert recommended_context_window("shared_public_sharegpt_boundary") == 32768