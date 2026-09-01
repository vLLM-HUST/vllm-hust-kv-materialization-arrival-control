import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "g0_formal", ROOT / "scripts" / "rebuild_g0_formal.py"
)
g0 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(g0)


def test_cell_evidence_separates_materialization_from_generic_throttling() -> None:
    def run(p95: float, goodput: float, peak: int, wait: float) -> dict:
        return {
            "ttft_ms": {"p95": p95},
            "goodput_rps": goodput,
            "materialization": {
                "peak_bytes_in_flight": peak,
                "connector_queue_wait_ms_p95": wait,
                "layer_ready_wait_ms_p95": wait,
            },
        }

    rounds = []
    for _ in range(3):
        rounds.append(
            {
                "no_control": run(120, 10, 4096, 2.0),
                "materialization_paced_oracle": run(100, 9.8, 1024, 0.5),
                "concurrency_cap": run(110, 7, 1024, 0.5),
                "request_token_bucket": run(115, 8, 1024, 0.5),
            }
        )
    evidence = g0.cell_evidence(rounds)
    assert evidence["reproducible_tail_gate"] is True
    assert evidence["materialization_counter_gate"] is True
    assert evidence["capacity_preserving_gate"] is True
    assert evidence["generic_equivalent_stop"] is False


def test_tail_repeat_gate_uses_preregistered_three_repeat_median() -> None:
    def run(p95: float, peak: int) -> dict:
        return {
            "ttft_ms": {"p95": p95},
            "goodput_rps": 10,
            "materialization": {
                "peak_bytes_in_flight": peak,
                "connector_queue_wait_ms_p95": 1,
                "layer_ready_wait_ms_p95": 1,
            },
        }

    rounds = []
    for oracle_p95 in (93, 90, 89):
        rounds.append(
            {
                "no_control": run(100, 4096),
                "materialization_paced_oracle": run(oracle_p95, 1024),
                "concurrency_cap": run(99, 1024),
                "request_token_bucket": run(99, 1024),
            }
        )
    evidence = g0.cell_evidence(rounds)
    assert evidence["repeats_meeting_tail_gate"] == 2
    assert evidence["reproducible_tail_gate"] is True
    ci = evidence["median_p95_regression_bootstrap_ci"]
    assert ci["replicates"] == 27
    assert ci["sampling_unit"] == "paired_server_lifecycle"


def test_exact_paired_lifecycle_bootstrap_is_deterministic() -> None:
    first = g0.paired_lifecycle_bootstrap_median([2.0, 8.0, 18.0])
    second = g0.paired_lifecycle_bootstrap_median([2.0, 8.0, 18.0])
    assert first == second
    assert first["lower_pct"] == 2.0
    assert first["upper_pct"] == 18.0
    assert first["replicates"] == 27


def test_real_run_loader_fails_closed_on_decision_coverage(tmp_path: Path) -> None:
    for relative in ("benchmark", "raw", "parsed"):
        (tmp_path / relative).mkdir()
    requests = [
        {
            "request_id": f"r{index}",
            "ok": True,
            "http_status": 200,
            "output_sha256": "a" * 64,
            "output_tokens": 8,
        }
        for index in range(64)
    ]
    (tmp_path / "benchmark/request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in requests), encoding="utf-8"
    )
    (tmp_path / "benchmark/random-online.json").write_text(
        json.dumps(
            {
                "arm": "no_control",
                "requests": 64,
                "correctness_rate": 1.0,
                "ttft_ms": {"p50": 1, "p95": 1, "p99": 1},
                "e2e_ms": {"mean": 2, "p95": 2},
                "tpot_ms": {"mean": 1, "p95": 1},
                "throughput_rps": 1,
                "goodput_rps": 1,
                "controls": {
                    "minimum_retrieve_tokens": 0,
                    "fixed_prefetch_depth": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    connector = {
        "activation": {
            "connector_config_events": 1,
            "decision_request_ids": 0,
            "decision_counts": {},
            "all_transfer_results_ok": True,
            "transfer_starts": 0,
        },
        "materialization": {},
        "resources": {},
    }
    (tmp_path / "parsed/g0_connector_summary.json").write_text(
        json.dumps(connector), encoding="utf-8"
    )
    (tmp_path / "raw/g0_connector_telemetry.jsonl").write_text("{}\n")
    (tmp_path / "raw/g0_resource_samples.jsonl").write_text("{}\n")
    spec = {
        "sequence": 1,
        "workload": "burstgpt",
        "burst_intensity": "moderate",
        "repeat": 1,
        "arm": "no_control",
    }
    try:
        g0.load_run(tmp_path, spec)
    except ValueError as exc:
        assert "decision coverage" in str(exc)
    else:
        raise AssertionError("missing runtime decisions were accepted")


def test_frozen_frontier_has_three_budgets_per_cell_and_repeat() -> None:
    manifest = {
        "repeats": 3,
        "schedule": [
            {"workload": workload}
            for workload in ("burstgpt", "servegen")
            for _ in range(48)
        ],
    }
    specs = g0.frontier_specs(manifest)
    assert len(specs) == 36
    assert [spec["sequence"] for spec in specs] == list(range(97, 133))
    assert {spec["budget"] for spec in specs} == set(g0.FRONTIER_BUDGETS)


def test_pathology_table_and_svg_are_dependency_free(tmp_path: Path) -> None:
    report = {
        "runs": [
            {
                "workload": "burstgpt",
                "burst_intensity": "high",
                "arm": arm,
                "reuse_pressure": [
                    {
                        "reuse_tokens": 128,
                        "requests": 2,
                        "requested_bytes_mean": 1024,
                        "connector_queue_wait_ms_p95": 0.2,
                        "layer_ready_wait_ms_p95": wait,
                        "bytes_in_flight_p95": 2048,
                    }
                ],
            }
            for arm, wait in (
                ("no_control", 2.0),
                ("materialization_paced_oracle", 0.5),
            )
        ]
    }
    rows = g0.pathology_rows(report)
    csv_path, svg_path = tmp_path / "pathology.csv", tmp_path / "pathology.svg"
    g0.write_pathology_csv(rows, csv_path)
    g0.write_pathology_svg(rows, svg_path)
    assert "reuse_tokens" in csv_path.read_text()
    assert "Layer-ready wait p95" in svg_path.read_text()


def test_complete_cell_emits_both_preregistered_fail_fast_triggers() -> None:
    triggers = g0.preregistered_stop_triggers(
        {
            "servegen/moderate": {
                "reproducible_tail_gate": False,
                "materialization_counter_gate": True,
                "generic_equivalent_stop": True,
            }
        }
    )
    assert triggers == [
        {
            "cell": "servegen/moderate",
            "trigger": "tail_pathology_not_reproducible",
        },
        {
            "cell": "servegen/moderate",
            "trigger": "generic_baseline_equivalent",
        },
    ]
