from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "paper"
    / "kv_materialization_control"
    / "experiments"
    / "run_openai_workloads.py"
)
SPEC = importlib.util.spec_from_file_location(
    "kv_materialization_live_driver", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_api_url_handles_base_with_v1() -> None:
    assert (
        MODULE.build_api_url("https://api.sage.org.ai/v1", "chat/completions")
        == "https://api.sage.org.ai/v1/chat/completions"
    )


def test_build_api_url_handles_base_without_v1() -> None:
    assert (
        MODULE.build_api_url("http://127.0.0.1:8011", "chat/completions")
        == "http://127.0.0.1:8011/v1/chat/completions"
    )


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


def test_send_request_records_stream_ttft_usage_and_raw_events(
    monkeypatch, tmp_path
) -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            yield b'data: {"id":"resp-1","choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}\n'
            yield b'data: {"id":"resp-1","choices":[{"delta":{"content":"hello"},"finish_reason":null}]}\n'
            yield b'data: {"id":"resp-1","choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":1}}\n'
            yield b"data: [DONE]\n"

    monkeypatch.setattr(MODULE, "urlopen", lambda request, timeout: Response())
    request = SimpleNamespace(
        request_id="req-1",
        workload_case="case-a",
        workload_family="family-a",
        primary_anchor_id="anchor-1",
        secondary_anchor_ids=(),
        shared_prefix_tokens=8,
        reuse_confidence=0.9,
        home_rank=0,
        turn_index=1,
        prompt="prompt",
        prompt_tokens=12,
        output_tokens=4,
    )
    requests_output = tmp_path / "requests.jsonl"

    result = MODULE.send_request(
        "http://127.0.0.1:8011",
        "model",
        request,
        None,
        None,
        requests_output,
    )

    assert result.ok is True
    assert result.ttft_s is not None
    assert result.generated_text == "hello"
    assert result.prompt_tokens_actual == 12
    assert result.completion_tokens_actual == 1
    assert result.finish_reason == "stop"
    assert len(result.raw_events) == 3
    assert requests_output.read_text().count("\n") == 1
