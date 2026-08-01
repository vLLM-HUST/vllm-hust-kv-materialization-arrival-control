from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

try:
    from .aggregate_online_results import FORMAL_LABEL, build_artifacts
    from .validate_online_bundle import validate_bundle
except ImportError:  # Direct script execution from the experiments directory.
    from aggregate_online_results import FORMAL_LABEL, build_artifacts
    from validate_online_bundle import validate_bundle


def assert_validation_current(bundle: Path) -> None:
    committed_path = bundle / "validation.json"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    recomputed = validate_bundle(bundle, expected_evidence_label=FORMAL_LABEL)
    if committed != recomputed:
        raise ValueError(f"stale validation.json: {bundle}")
    raw_check = recomputed.get("raw_summary_verification", {})
    if not raw_check.get("valid"):
        raise ValueError(f"raw request summary verification failed: {bundle}")


def assert_generated_current(expected_dir: Path, rebuilt_dir: Path) -> None:
    expected_files = {
        path.relative_to(expected_dir)
        for path in expected_dir.rglob("*")
        if path.is_file()
    }
    rebuilt_files = {
        path.relative_to(rebuilt_dir)
        for path in rebuilt_dir.rglob("*")
        if path.is_file()
    }
    if expected_files != rebuilt_files:
        raise ValueError(
            "generated artifact set is stale: "
            f"missing={sorted(rebuilt_files - expected_files)}, "
            f"extra={sorted(expected_files - rebuilt_files)}"
        )
    for relative in sorted(expected_files):
        expected = expected_dir / relative
        rebuilt = rebuilt_dir / relative
        if expected.read_bytes() != rebuilt.read_bytes():
            raise ValueError(f"generated artifact is stale: {relative}")


def verify_rebuild(input_dir: Path, generated_dir: Path) -> None:
    validation_paths = sorted(input_dir.rglob("validation.json"))
    if not validation_paths:
        raise ValueError("suite contains no validation.json files")
    for validation_path in validation_paths:
        assert_validation_current(validation_path.parent)

    with tempfile.TemporaryDirectory(prefix="m1-online-rebuild-") as temporary:
        rebuilt_dir = Path(temporary)
        build_artifacts(input_dir, rebuilt_dir)
        assert_generated_current(generated_dir, rebuilt_dir)

    print(
        f"verified {len(validation_paths)} raw bundles and byte-identical generated artifacts"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail closed on stale M1 validation, raw summaries, or generated output."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--generated-dir", required=True)
    args = parser.parse_args()
    verify_rebuild(Path(args.input_dir).resolve(), Path(args.generated_dir).resolve())


if __name__ == "__main__":
    main()
