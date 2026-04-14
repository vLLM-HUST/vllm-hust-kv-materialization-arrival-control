from __future__ import annotations

from vllm_kv_materialization.live_control import HEADER_PRIMARY_ANCHOR
from vllm_kv_materialization.live_control import HEADER_REUSE_CONFIDENCE
from vllm_kv_materialization.live_control import HEADER_SHARED_PREFIX_TOKENS
from vllm_kv_materialization.live_control import HEADER_TURN_INDEX
from vllm_kv_materialization.live_control import apply_runtime_control
from vllm_kv_materialization.live_control import bind_request_headers
from vllm_kv_materialization.live_control import compute_runtime_control
from vllm_kv_materialization.live_control import estimate_reusable_prefix_tokens
from vllm_kv_materialization.live_control import observe_request
from vllm_kv_materialization.live_control import reset_request_headers


def test_estimate_reusable_prefix_tokens_prefers_header_value() -> None:
    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-a",
        HEADER_SHARED_PREFIX_TOKENS: "640",
        HEADER_TURN_INDEX: "0",
    }

    assert estimate_reusable_prefix_tokens(headers, 1024) == 640


def test_observe_request_returns_full_reuse_for_seen_anchor(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)
    monkeypatch.setenv("VLLM_KV_TRANSFER_BANDWIDTH_GBPS", "200")

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-b",
        HEADER_SHARED_PREFIX_TOKENS: "1024",
        HEADER_TURN_INDEX: "1",
        HEADER_REUSE_CONFIDENCE: "0.98",
    }

    first_token = bind_request_headers(headers)
    try:
        first = observe_request("req-first", 1400, 64)
    finally:
        reset_request_headers(first_token)

    second_token = bind_request_headers(headers)
    try:
        second = observe_request("req-second", 1400, 64)
    finally:
        reset_request_headers(second_token)

    assert first.reusable_prefix_tokens == 1024
    assert second.decision in {"full_reuse", "partial_reuse"}


def test_compute_runtime_control_uses_unique_salt_for_recompute(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-c",
        HEADER_SHARED_PREFIX_TOKENS: "0",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.0",
    }

    token = bind_request_headers(headers)
    try:
        observation, plan = compute_runtime_control("req-c", 1024, 64)
    finally:
        reset_request_headers(token)

    assert observation.decision == "recompute"
    assert plan.effective_decision == "recompute"
    assert plan.cache_salt is not None
    assert "req-c" in plan.cache_salt


def test_compute_runtime_control_marks_partial_as_degraded_full_reuse(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-d",
        HEADER_SHARED_PREFIX_TOKENS: "1200",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.2",
    }

    token = bind_request_headers(headers)
    try:
        observation, plan = compute_runtime_control("req-d", 1600, 64)
    finally:
        reset_request_headers(token)

    assert observation.decision == "partial_reuse"
    assert observation.runtime_effective_decision == "full_reuse"
    assert plan.decision_supported is False
    assert "partial_reuse_degraded" in observation.runtime_control_path


def test_apply_runtime_control_injects_cache_salt() -> None:
    prompt = {"type": "token", "prompt_token_ids": [1, 2, 3]}
    _, plan = compute_runtime_control("req-e", 0, 0)
    plan = type(plan)(
        observed_decision=plan.observed_decision,
        effective_decision=plan.effective_decision,
        control_path=plan.control_path,
        cache_salt="kvmat:anchor:test",
        decision_supported=plan.decision_supported,
    )

    controlled = apply_runtime_control(prompt, plan)

    assert controlled["cache_salt"] == "kvmat:anchor:test"
    assert "cache_salt" not in prompt