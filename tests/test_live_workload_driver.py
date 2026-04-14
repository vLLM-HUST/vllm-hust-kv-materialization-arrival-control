from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = (
	Path(__file__).resolve().parents[1]
	/ "paper"
	/ "kv_materialization_control"
	/ "experiments"
	/ "run_openai_workloads.py"
)
SPEC = importlib.util.spec_from_file_location("kv_materialization_live_driver", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_api_url_handles_base_with_v1() -> None:
	assert MODULE.build_api_url("https://api.sage.org.ai/v1", "chat/completions") == "https://api.sage.org.ai/v1/chat/completions"


def test_build_api_url_handles_base_without_v1() -> None:
	assert MODULE.build_api_url("http://127.0.0.1:8011", "chat/completions") == "http://127.0.0.1:8011/v1/chat/completions"


def test_build_headers_adds_auth_and_user_agent() -> None:
	headers = MODULE.build_headers("test-key", "python-httpx/0.28.1")

	assert headers["Authorization"] == "Bearer test-key"
	assert headers["User-Agent"] == "python-httpx/0.28.1"
	assert headers["Content-Type"] == "application/json"


def test_build_workload_headers_adds_anchor_metadata() -> None:
	class WorkloadRequest:
		request_id = "req-1"
		workload_case = "case-a"
		workload_family = "family-a"
		primary_anchor_id = "anchor-1"
		secondary_anchor_ids = ("sec-1", "sec-2")
		shared_prefix_tokens = 512
		reuse_confidence = 0.9
		home_rank = 3
		turn_index = 2

	headers = MODULE.build_workload_headers(WorkloadRequest())

	assert headers["X-Request-Id"] == "req-1"
	assert headers["X-KV-Primary-Anchor-Id"] == "anchor-1"
	assert headers["X-KV-Secondary-Anchor-Ids"] == "sec-1,sec-2"
	assert headers["X-KV-Shared-Prefix-Tokens"] == "512"
	assert headers["X-KV-Turn-Index"] == "2"