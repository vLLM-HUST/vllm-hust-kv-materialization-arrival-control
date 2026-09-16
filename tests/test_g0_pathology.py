import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("g0", ROOT / "scripts" / "g0_pathology.py")
g0 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(g0)


def test_overlay_preserves_trace_order_and_is_auditable(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"id":"a","timestamp":3,"prompt":"hello"}\n{"id":"b","timestamp":4,"prompt":"world"}\n')
    overlay = tmp_path / "overlay.jsonl"
    custody = g0.write_overlay(trace, overlay, "burstgpt", "high")
    rows = [json.loads(line) for line in overlay.read_text().splitlines()]
    assert [row["request_id"] for row in rows] == ["a", "b"]
    assert [row["sequence_index"] for row in rows] == [0, 1]
    assert custody["trace_sha256"] and custody["overlay_sha256"]


def test_bundle_without_materialization_signal_fails_closed(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"; bundle.mkdir()
    (bundle / "run_manifest.json").write_text(json.dumps({"workload": "burstgpt", "burst_intensity": "high", "repeat": 1, "arm": "no_control"}))
    (bundle / "request_results.jsonl").write_text(json.dumps({"request_id": "a", "ok": True, "ttft_ms": 1, "e2e_ms": 2, "tpot_ms": 1, "output_tokens": 1}) + "\n")
    (bundle / "materialization_telemetry.jsonl").write_text(json.dumps({"request_id": "a"}) + "\n")
    try:
        g0.load_bundle(bundle)
    except ValueError as exc:
        assert "telemetry activation failure" in str(exc)
    else:
        raise AssertionError("missing materialization telemetry was accepted")


def test_low_control_removes_instantaneous_source_burst(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        '{"id":"a","timestamp":3,"prompt":"a"}\n'
        '{"id":"b","timestamp":3,"prompt":"b"}\n'
        '{"id":"c","timestamp":4,"prompt":"c"}\n'
    )
    overlay = tmp_path / "low.jsonl"
    custody = g0.write_overlay(trace, overlay, "burstgpt", "low_control")
    rows = [json.loads(line) for line in overlay.read_text().splitlines()]
    assert [row["arrival_s"] for row in rows] == [0.0, 1.0, 2.0]
    assert custody["arrival_transform"] == "uniform_low_concurrency"
