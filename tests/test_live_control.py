from __future__ import annotations

import hashlib
from types import SimpleNamespace

from vllm_kv_materialization.live_control import (
    HEADER_PRIMARY_ANCHOR,
    HEADER_REQUEST_ID,
    HEADER_REUSE_CONFIDENCE,
    HEADER_SECONDARY_ANCHORS,
    HEADER_SHARED_PREFIX_TOKENS,
    HEADER_TURN_INDEX,
    PARTIAL_REUSE_ALIGNMENT_FALLBACK_REASON,
    PARTIAL_REUSE_FALLBACK_REASON,
    PARTIAL_REUSE_RUNTIME_REALIGN_TO_FULL_REUSE,
    RUNTIME_KV_TRANSFER_CONTROL_KEY,
    RUNTIME_SUPPORT_FALLBACK,
    apply_runtime_control,
    bind_request_headers,
    build_runtime_control_extra_args,
    compute_runtime_control,
    estimate_reusable_prefix_tokens,
    merge_runtime_control_extra_args,
    observe_request,
    reset_request_headers,
)


class _RecordingCoordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[object, int]] = []
        self.single_type_managers: tuple[object, ...] = ()

    def cache_blocks(self, request: object, num_computed_tokens: int) -> None:
        self.calls.append((request, num_computed_tokens))


def _runtime_control_payload(
    decision: str,
    *,
    prompt_tokens: int,
    target_reuse_tokens: int,
    cache_salt: str | None = "kvmat:anchor:test",
    segmented_tail_cache_salt: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "observed_decision": decision,
        "effective_decision": decision,
        "control_path": "test",
        "cache_salt": cache_salt,
        "decision_supported": True,
        "support_tier": "native_runtime_action",
        "fallback_reason": None,
        "target_reuse_tokens": target_reuse_tokens,
        "target_tail_tokens": prompt_tokens - target_reuse_tokens,
        "segmented_tail_cache_salt": segmented_tail_cache_salt,
        "requires_segmented_materialization": decision == "partial_reuse",
    }


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


def test_fixed_recompute_policy_forces_native_recompute(monkeypatch) -> None:
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "always_recompute")
    monkeypatch.setenv("VLLM_KV_RUNTIME_BLOCK_SIZE", "128")
    token = bind_request_headers(
        {
            HEADER_PRIMARY_ANCHOR: "anchor-fixed-recompute",
            HEADER_SHARED_PREFIX_TOKENS: "1024",
            HEADER_REUSE_CONFIDENCE: "0.99",
        }
    )
    try:
        observation, plan = compute_runtime_control("req-fixed-recompute", 1400, 64)
    finally:
        reset_request_headers(token)

    assert observation.policy_mode == "always_recompute"
    assert observation.decision == "recompute"
    assert observation.rationale == "fixed_policy_always_recompute"
    assert plan.effective_decision == "recompute"
    assert plan.target_reuse_tokens == 0


def test_fixed_full_reuse_policy_forces_native_full_reuse(monkeypatch) -> None:
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "always_full_reuse")
    token = bind_request_headers(
        {
            HEADER_PRIMARY_ANCHOR: "anchor-fixed-full",
            HEADER_SHARED_PREFIX_TOKENS: "1024",
            HEADER_REUSE_CONFIDENCE: "0.01",
        }
    )
    try:
        observation, plan = compute_runtime_control("req-fixed-full", 1400, 64)
    finally:
        reset_request_headers(token)

    assert observation.policy_mode == "always_full_reuse"
    assert observation.decision == "full_reuse"
    assert observation.rationale == "fixed_policy_always_full_reuse"
    assert plan.effective_decision == "full_reuse"
    assert plan.target_reuse_tokens == 1024


def test_compute_runtime_control_marks_partial_as_degraded_full_reuse(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-d",
        HEADER_SECONDARY_ANCHORS: "tenant::0,shared-scaffold::2,tail-class::interactive",
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
    assert observation.runtime_target_reuse_tokens == observation.reusable_prefix_tokens
    assert (
        observation.runtime_target_tail_tokens
        == 1600 - observation.reusable_prefix_tokens
    )
    assert plan.decision_supported is False
    assert plan.cache_salt == "kvmat:anchor:shared-scaffold::2"
    assert observation.runtime_support_tier == RUNTIME_SUPPORT_FALLBACK
    assert observation.runtime_fallback_reason == PARTIAL_REUSE_FALLBACK_REASON
    assert plan.fallback_reason == PARTIAL_REUSE_FALLBACK_REASON
    assert "partial_reuse_fallback" in observation.runtime_control_path

    runtime_hint = build_runtime_control_extra_args(plan)[
        RUNTIME_KV_TRANSFER_CONTROL_KEY
    ]

    assert runtime_hint["target_reuse_tokens"] == observation.reusable_prefix_tokens
    assert runtime_hint["cache_salt"] == plan.cache_salt
    assert (
        runtime_hint["target_tail_tokens"] == 1600 - observation.reusable_prefix_tokens
    )
    assert runtime_hint["requires_segmented_materialization"] is True


def test_partial_reuse_fallback_keeps_primary_anchor_without_scaffold(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-fallback",
        HEADER_SECONDARY_ANCHORS: "tenant::1,band::0",
        HEADER_SHARED_PREFIX_TOKENS: "1200",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.2",
    }

    token = bind_request_headers(headers)
    try:
        _, plan = compute_runtime_control("req-fallback", 1600, 64)
    finally:
        reset_request_headers(token)

    assert plan.cache_salt == "kvmat:anchor:anchor-fallback"


def test_merge_runtime_control_extra_args_preserves_existing_fields(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-merge",
        HEADER_SHARED_PREFIX_TOKENS: "1200",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.2",
    }

    token = bind_request_headers(headers)
    try:
        _, plan = compute_runtime_control("req-merge", 1600, 64)
    finally:
        reset_request_headers(token)

    merged = merge_runtime_control_extra_args(
        {"remote_engine_id": "prefill-0", "remote_block_ids": [1, 2]},
        plan,
    )

    assert merged["remote_engine_id"] == "prefill-0"
    assert merged["remote_block_ids"] == [1, 2]
    assert merged[RUNTIME_KV_TRANSFER_CONTROL_KEY]["control_path"] == plan.control_path


def test_apply_runtime_control_injects_cache_salt() -> None:
    prompt = {"type": "token", "prompt_token_ids": [1, 2, 3]}
    _, plan = compute_runtime_control("req-e", 0, 0)
    plan = type(plan)(
        observed_decision=plan.observed_decision,
        effective_decision=plan.effective_decision,
        control_path=plan.control_path,
        cache_salt="kvmat:anchor:test",
        segmented_tail_cache_salt=plan.segmented_tail_cache_salt,
        target_reuse_tokens=plan.target_reuse_tokens,
        target_tail_tokens=plan.target_tail_tokens,
        decision_supported=plan.decision_supported,
        support_tier=plan.support_tier,
        fallback_reason=plan.fallback_reason,
    )

    controlled = apply_runtime_control(prompt, plan)

    assert controlled["cache_salt"] == "kvmat:anchor:test"
    assert "cache_salt" not in prompt


def test_compute_runtime_control_aligns_partial_to_runtime_blocks(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)
    monkeypatch.setenv("VLLM_KV_RUNTIME_BLOCK_SIZE", "128")

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-align",
        HEADER_SECONDARY_ANCHORS: "tenant::0,shared-scaffold::2,tail-class::interactive",
        HEADER_SHARED_PREFIX_TOKENS: "1200",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.2",
    }

    token = bind_request_headers(headers)
    try:
        observation, plan = compute_runtime_control("req-align", 1600, 64)
    finally:
        reset_request_headers(token)

    assert observation.decision == "partial_reuse"
    assert plan.effective_decision == "partial_reuse"
    assert plan.decision_supported is True
    assert plan.target_reuse_tokens % 128 == 0
    assert 0 < plan.target_reuse_tokens <= observation.reused_tokens
    assert plan.cache_salt == "kvmat:anchor:shared-scaffold::2"
    assert plan.segmented_tail_cache_salt == "kvmat:recompute:anchor-align:req-align"
    assert plan.fallback_reason == PARTIAL_REUSE_ALIGNMENT_FALLBACK_REASON


def test_old_seam_truthfully_falls_partial_back_to_full_reuse(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)
    monkeypatch.setenv("VLLM_KV_RUNTIME_SEAM", "old")
    monkeypatch.setenv("VLLM_KV_RUNTIME_BLOCK_SIZE", "128")
    token = bind_request_headers(
        {
            HEADER_REQUEST_ID: "req-old",
            HEADER_PRIMARY_ANCHOR: "anchor-old",
            HEADER_SECONDARY_ANCHORS: "tenant::0,shared-scaffold::2,tail-class::interactive",
            HEADER_SHARED_PREFIX_TOKENS: "1200",
            HEADER_REUSE_CONFIDENCE: "0.2",
        }
    )
    try:
        observation, plan = compute_runtime_control("req-old", 1600, 64)
    finally:
        reset_request_headers(token)

    assert observation.decision == "partial_reuse"
    assert plan.effective_decision == "full_reuse"
    assert plan.decision_supported is False
    assert plan.fallback_reason == PARTIAL_REUSE_FALLBACK_REASON


def test_compute_runtime_control_realigns_unusable_partial_to_full_reuse(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)
    monkeypatch.setenv("VLLM_KV_RUNTIME_BLOCK_SIZE", "4096")

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-recompute",
        HEADER_SECONDARY_ANCHORS: "tenant::0,shared-scaffold::2,tail-class::interactive",
        HEADER_SHARED_PREFIX_TOKENS: "1200",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.2",
    }

    token = bind_request_headers(headers)
    try:
        _, plan = compute_runtime_control("req-recompute", 1600, 64)
    finally:
        reset_request_headers(token)

    assert plan.effective_decision == "full_reuse"
    assert plan.target_reuse_tokens == 1200
    assert plan.fallback_reason == PARTIAL_REUSE_RUNTIME_REALIGN_TO_FULL_REUSE


def test_partial_reuse_caps_cacheable_tokens_to_reuse_boundary() -> None:
    from vllm.sampling_params import SamplingParams
    from vllm.v1.core.kv_cache_manager import KVCacheManager
    from vllm.v1.request import Request

    manager = object.__new__(KVCacheManager)
    manager.enable_caching = True
    manager.log_stats = False
    manager.hash_block_size = 128
    manager.coordinator = _RecordingCoordinator()
    manager.block_pool = SimpleNamespace(get_usage=lambda: 0.0)
    manager._emit_materialization_event = lambda *args, **kwargs: None

    sampling_params = SamplingParams.from_optional(
        max_tokens=1,
        extra_args={
            RUNTIME_KV_TRANSFER_CONTROL_KEY: _runtime_control_payload(
                "partial_reuse",
                prompt_tokens=1536,
                target_reuse_tokens=768,
                segmented_tail_cache_salt="kvmat:segment:test",
            )
        },
    )
    request = Request("req-cache-cap", list(range(1536)), sampling_params, None)

    KVCacheManager.cache_blocks(manager, request, 1536)

    assert manager.coordinator.calls == [(request, 768)]


def test_partial_reuse_exports_segmented_tail_salt(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)
    monkeypatch.setenv("VLLM_KV_RUNTIME_BLOCK_SIZE", "128")

    headers = {
        HEADER_PRIMARY_ANCHOR: "anchor-tail-salt",
        HEADER_SECONDARY_ANCHORS: "tenant::0,shared-scaffold::2",
        HEADER_SHARED_PREFIX_TOKENS: "1024",
        HEADER_TURN_INDEX: "0",
        HEADER_REUSE_CONFIDENCE: "0.2",
    }

    token = bind_request_headers(headers)
    try:
        _, plan = compute_runtime_control("req-tail-salt", 1536, 64)
    finally:
        reset_request_headers(token)

    runtime_hint = build_runtime_control_extra_args(plan)[
        RUNTIME_KV_TRANSFER_CONTROL_KEY
    ]

    assert plan.effective_decision == "partial_reuse"
    assert runtime_hint["cache_salt"] == plan.cache_salt
    assert runtime_hint["segmented_tail_cache_salt"] == plan.segmented_tail_cache_salt
    assert (
        runtime_hint["segmented_tail_cache_salt"]
        == "kvmat:recompute:anchor-tail-salt:req-tail-salt"
    )


def test_partial_reuse_resets_tail_hash_chain_at_boundary() -> None:
    from vllm.sampling_params import SamplingParams
    from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
    from vllm.v1.request import Request

    def _stable_hash(value: object) -> bytes:
        return hashlib.sha256(repr(value).encode("utf-8")).digest()

    init_none_hash(_stable_hash)
    block_hasher = get_request_block_hasher(2, _stable_hash)
    runtime_control = _runtime_control_payload(
        "partial_reuse",
        prompt_tokens=8,
        target_reuse_tokens=4,
        segmented_tail_cache_salt="kvmat:segment:test",
    )
    sampling_params = SamplingParams.from_optional(
        max_tokens=1,
        extra_args={RUNTIME_KV_TRANSFER_CONTROL_KEY: runtime_control},
    )

    request_a = Request(
        "req-segment-a",
        [1, 2, 3, 4, 9, 10, 11, 12],
        sampling_params,
        None,
        cache_salt="kvmat:anchor:test",
        block_hasher=block_hasher,
    )
    request_b = Request(
        "req-segment-b",
        [5, 6, 7, 8, 9, 10, 11, 12],
        sampling_params,
        None,
        cache_salt="kvmat:anchor:test",
        block_hasher=block_hasher,
    )

    assert request_a.block_hashes[:2] != request_b.block_hashes[:2]
    assert request_a.block_hashes[2:] == request_b.block_hashes[2:]


def test_full_reuse_keeps_cacheable_tokens_uncapped() -> None:
    from vllm.sampling_params import SamplingParams
    from vllm.v1.core.kv_cache_manager import KVCacheManager
    from vllm.v1.request import Request

    manager = object.__new__(KVCacheManager)
    manager.enable_caching = True
    manager.log_stats = False
    manager.hash_block_size = 128
    manager.coordinator = _RecordingCoordinator()
    manager.block_pool = SimpleNamespace(get_usage=lambda: 0.0)
    manager._emit_materialization_event = lambda *args, **kwargs: None

    sampling_params = SamplingParams.from_optional(
        max_tokens=1,
        extra_args={
            RUNTIME_KV_TRANSFER_CONTROL_KEY: _runtime_control_payload(
                "full_reuse",
                prompt_tokens=1536,
                target_reuse_tokens=768,
            )
        },
    )
    request = Request("req-cache-full", list(range(1536)), sampling_params, None)

    KVCacheManager.cache_blocks(manager, request, 1536)

    assert manager.coordinator.calls == [(request, 1536)]
