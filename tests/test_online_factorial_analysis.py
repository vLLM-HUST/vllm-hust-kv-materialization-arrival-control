from __future__ import annotations

import math

import pytest

from paper.kv_materialization_control.experiments.aggregate_online_results import (
    FACTORIAL_WORKLOADS,
    PRIMARY_METRICS,
    T_CRITICAL_95_DF2,
    _mean_ci,
    factorial_effects,
)


def factorial_runs(
    values: dict[tuple[str, str], float] | None = None,
) -> list[dict]:
    cell_values = values or {
        ("old", "baseline"): 100.0,
        ("old", "tuned"): 120.0,
        ("segmented", "baseline"): 200.0,
        ("segmented", "tuned"): 220.0,
    }
    runs = []
    for workload in FACTORIAL_WORKLOADS:
        for round_number in (1, 2, 3):
            for sequence, ((seam, condition), value) in enumerate(
                cell_values.items(), start=1
            ):
                row = {
                    "workload": workload,
                    "seam": seam,
                    "condition": condition,
                    "bundle": (
                        f"{workload}/{seam}_{condition}/"
                        f"round_{round_number:02d}_sequence_{sequence:02d}"
                    ),
                }
                row.update({metric: value for metric in PRIMARY_METRICS})
                runs.append(row)
    return runs


def test_factorial_effects_mark_interaction_as_percentage_points() -> None:
    _, summaries = factorial_effects(factorial_runs())
    first_metric = [
        row
        for row in summaries
        if row["workload"] == FACTORIAL_WORKLOADS[0]
        and row["metric"] == PRIMARY_METRICS[0]
    ]
    by_effect = {row["effect"]: row for row in first_metric}

    assert by_effect["seam_main"]["relative_delta_mean"] == 90.909091
    assert by_effect["tuning_main"]["relative_delta_mean"] == 13.333333
    assert by_effect["interaction"]["relative_delta_mean"] == -10.0
    assert by_effect["interaction"]["relative_delta_unit"] == "percentage_points"
    assert by_effect["interaction"]["interval_interpretation"] == (
        "descriptive_exploratory"
    )
    assert by_effect["segmented_tuned_vs_old_baseline"]["relative_delta_mean"] == 120.0
    assert by_effect["seam_main"]["relative_delta_unit"] == "percent"


def test_mean_ci_uses_nonzero_sample_variance_and_df2_t_critical() -> None:
    values = [1.0, 2.0, 4.0]
    center, low, high = _mean_ci(values)
    expected_half_width = T_CRITICAL_95_DF2 * math.sqrt(7.0 / 3.0) / math.sqrt(3.0)

    assert center == pytest.approx(7.0 / 3.0)
    assert center - low == expected_half_width
    assert high - center == expected_half_width


@pytest.mark.parametrize("defect", ["missing", "duplicate", "misaligned"])
def test_factorial_effects_fail_close_on_bad_rounds(defect: str) -> None:
    runs = factorial_runs()
    if defect == "missing":
        runs.pop()
    elif defect == "duplicate":
        runs.append(dict(runs[-1]))
    else:
        runs[-1] = dict(runs[-1])
        runs[-1]["bundle"] = runs[-1]["bundle"].replace("round_03", "round_04")

    with pytest.raises(ValueError, match="round|duplicate|misaligned"):
        factorial_effects(runs)


def test_factorial_effects_fail_close_on_zero_denominator() -> None:
    values = {
        ("old", "baseline"): 0.0,
        ("old", "tuned"): 0.0,
        ("segmented", "baseline"): 100.0,
        ("segmented", "tuned"): 110.0,
    }

    with pytest.raises(ValueError, match="zero denominator"):
        factorial_effects(factorial_runs(values))
