"""Only reviewed code/configuration and forwarding documents remain in migrated collections."""

import subprocess
from pathlib import Path

PREFIXES = [
    "paper/kv_materialization_control/experiments/results/",
    "docs/g0/",
    "docs/wavemat/",
]
RETAINED = [
    "docs/g0/CARRIER_GOVERNANCE_CORRECTION_20260901.md",
    "docs/g0/ISSUE17_FINAL_REPLY_20260831.md",
    "docs/g0/PREREGISTRATION_20260831.md",
    "docs/g0/README.md",
    "docs/g0/REVIEW_CORRECTIONS_20260901.md",
    "docs/g0/pilot_20260831.md",
    "docs/wavemat/ENV_PIN.md",
    "docs/wavemat/M0_UPSTREAM_AUDIT.md",
    "docs/wavemat/SEAM_GATE.md",
    "docs/wavemat/configs/mmc-local-tp1.conf",
    "docs/wavemat/configs/mmc-local-tp4.conf",
    "docs/wavemat/configs/mmc-local.conf",
    "docs/wavemat/configs/mmc-meta.conf",
    "paper/kv_materialization_control/experiments/results/m1_formal/README.md",
    "paper/kv_materialization_control/experiments/results/m1_formal_approved_complete_20260801/FACTORIAL_ANALYSIS.md",
    "paper/kv_materialization_control/experiments/results/m1_formal_approved_complete_20260801/README.md",
    "paper/kv_materialization_control/experiments/results/m1_formal_engine_accounted_complete_20260731/README.md",
    "paper/kv_materialization_control/experiments/results/m1_paired_dry_20260801T021223Z_f2ddea6/README.md",
    "paper/kv_materialization_control/experiments/results/m2_anchor_confirmation_20260803/README.md",
    "paper/kv_materialization_control/experiments/results/m2_anchor_pilot_20260803/README.md",
    "paper/kv_materialization_control/experiments/results/m2_candidate_pilot_20260803/README.md",
    "paper/kv_materialization_control/experiments/results/m2_catalog_closure_20260803/README.md",
    "paper/kv_materialization_control/experiments/results/m2_online_boundary_20260803/README.md",
]


def test_migrated_collection_boundary():
    root = Path(__file__).resolve().parents[1]
    actual = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--", *PREFIXES], text=True
    ).splitlines()
    assert set(actual) == set(RETAINED), (
        "Review new code or migrate original data to benchmark"
    )
