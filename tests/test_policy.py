from __future__ import annotations

from vllm_kv_materialization.policy import MaterializationDecision
from vllm_kv_materialization.policy import MaterializationPolicy
from vllm_kv_materialization.policy import MaterializationSignals


def test_policy_chooses_full_reuse_when_transfer_is_cheap() -> None:
    policy = MaterializationPolicy()
    outcome = policy.decide(
        MaterializationSignals(
            reusable_prefix_tokens=2048,
            remote_kv_bytes=64,
            transfer_time_ms=6.0,
            recompute_time_ms=20.0,
            queue_pressure=0.5,
            ttft_sensitive=True,
            reuse_confidence=0.95,
        )
    )
    assert outcome.decision is MaterializationDecision.FULL_REUSE
    assert outcome.reused_tokens == 2048


def test_policy_chooses_partial_reuse_for_midrange_case() -> None:
    policy = MaterializationPolicy(partial_reuse_floor_tokens=256)
    outcome = policy.decide(
        MaterializationSignals(
            reusable_prefix_tokens=800,
            remote_kv_bytes=32,
            transfer_time_ms=10.0,
            recompute_time_ms=12.0,
            queue_pressure=0.0,
            ttft_sensitive=False,
        )
    )
    assert outcome.decision is MaterializationDecision.PARTIAL_REUSE
    assert outcome.reused_tokens >= 256


def test_policy_chooses_recompute_for_small_reuse_window() -> None:
    policy = MaterializationPolicy()
    outcome = policy.decide(
        MaterializationSignals(
            reusable_prefix_tokens=64,
            remote_kv_bytes=8,
            transfer_time_ms=5.0,
            recompute_time_ms=4.0,
            queue_pressure=0.0,
            ttft_sensitive=False,
        )
    )
    assert outcome.decision is MaterializationDecision.RECOMPUTE


def test_policy_uses_partial_reuse_for_low_confidence_large_prefix() -> None:
    policy = MaterializationPolicy(partial_reuse_floor_tokens=256)
    outcome = policy.decide(
        MaterializationSignals(
            reusable_prefix_tokens=1200,
            remote_kv_bytes=64,
            transfer_time_ms=6.5,
            recompute_time_ms=9.5,
            queue_pressure=0.1,
            ttft_sensitive=True,
            reuse_confidence=0.25,
        )
    )
    assert outcome.decision is MaterializationDecision.PARTIAL_REUSE
    assert outcome.reused_tokens < 1200
