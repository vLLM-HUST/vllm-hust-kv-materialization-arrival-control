from paper.kv_materialization_control.experiments.aggregate_online_results import (
    FACTORIAL_WORKLOADS,
    PRIMARY_METRICS,
    factorial_effects,
)


def test_factorial_effects_use_matched_lifecycle_rounds() -> None:
    values = {
        ("old", "baseline"): 100.0,
        ("old", "tuned"): 110.0,
        ("segmented", "baseline"): 120.0,
        ("segmented", "tuned"): 132.0,
    }
    runs = []
    for workload in FACTORIAL_WORKLOADS:
        for round_number in (1, 2, 3):
            for (seam, condition), value in values.items():
                row = {
                    "workload": workload,
                    "seam": seam,
                    "condition": condition,
                    "bundle": (
                        f"{workload}/{seam}_{condition}/"
                        f"round_{round_number:02d}_sequence_{round_number:02d}"
                    ),
                }
                row.update({metric: value for metric in PRIMARY_METRICS})
                runs.append(row)

    round_rows, summaries = factorial_effects(runs)

    assert len(round_rows) == 2 * 3 * 4 * 3
    assert len(summaries) == 2 * 3 * 4
    first_metric = [
        row
        for row in summaries
        if row["workload"] == FACTORIAL_WORKLOADS[0]
        and row["metric"] == PRIMARY_METRICS[0]
    ]
    by_effect = {row["effect"]: row for row in first_metric}
    assert by_effect["seam_main"]["relative_delta_pct_mean"] == 20.0
    assert by_effect["tuning_main"]["relative_delta_pct_mean"] == 10.0
    assert by_effect["interaction"]["relative_delta_pct_mean"] == 0.0
    assert (
        by_effect["segmented_tuned_vs_old_baseline"]["relative_delta_pct_mean"]
        == 32.0
    )
    assert by_effect["seam_main"]["relative_delta_pct_ci95_low"] == 20.0
    assert by_effect["seam_main"]["relative_delta_pct_ci95_high"] == 20.0
