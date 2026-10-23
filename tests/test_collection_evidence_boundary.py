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
]


def test_migrated_collection_boundary():
    root = Path(__file__).resolve().parents[1]
    actual = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--", *PREFIXES], text=True
    ).splitlines()
    assert set(actual) == set(RETAINED), (
        "Review new code or migrate original data to benchmark"
    )
