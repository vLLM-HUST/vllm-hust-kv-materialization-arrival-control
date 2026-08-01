from __future__ import annotations

import json

import pytest

from paper.kv_materialization_control.experiments import verify_m1_online_rebuild
from paper.kv_materialization_control.experiments.validate_online_bundle import (
    verify_request_summary,
)


def request_result(request_id: str, latency_s: float, ttft_s: float) -> dict:
    return {
        "request_id": request_id,
        "ok": True,
        "latency_s": latency_s,
        "ttft_s": ttft_s,
    }


def test_raw_request_recompute_rejects_stale_summary() -> None:
    requests = [
        request_result("r1", 1.0, 0.1),
        request_result("r2", 3.0, 0.3),
    ]
    summary = {
        "requests": 2,
        "completed": 2,
        "failures": [],
        "mean_latency_ms": 999.0,
        "p95_latency_ms": 3000.0,
        "mean_ttft_ms": 200.0,
        "p95_ttft_ms": 300.0,
    }

    recomputed, errors = verify_request_summary(summary, requests)

    assert recomputed["mean_latency_ms"] == 2000.0
    assert errors == [
        "summary mean_latency_ms=999.0 does not match raw request result 2000.0"
    ]


def test_validation_comparison_rejects_stale_validation(monkeypatch, tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "validation.json").write_text(
        json.dumps({"valid": True, "version": "old"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        verify_m1_online_rebuild,
        "validate_bundle",
        lambda *args, **kwargs: {"valid": True, "version": "new"},
    )

    with pytest.raises(ValueError, match="stale validation"):
        verify_m1_online_rebuild.assert_validation_current(bundle)


def test_golden_comparison_rejects_stale_generated_file(tmp_path) -> None:
    expected = tmp_path / "expected"
    rebuilt = tmp_path / "rebuilt"
    expected.mkdir()
    rebuilt.mkdir()
    (expected / "table.csv").write_text("stale\n", encoding="utf-8")
    (rebuilt / "table.csv").write_text("fresh\n", encoding="utf-8")

    with pytest.raises(ValueError, match="generated artifact is stale"):
        verify_m1_online_rebuild.assert_generated_current(expected, rebuilt)
