import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "g0_custody", ROOT / "scripts" / "build_g0_raw_manifest.py"
)
custody = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(custody)


def test_manifest_detects_mutation_and_extra_file(tmp_path: Path) -> None:
    suite, runs = tmp_path / "suite", tmp_path / "runs"
    suite.mkdir()
    runs.mkdir()
    (suite / "suite_manifest.json").write_text("{}\n")
    (runs / "raw.jsonl").write_text('{"ok":true}\n')
    manifest = custody.build(suite, runs)
    assert custody.verify_tree(suite, manifest["suite_files"]) == []
    assert custody.verify_tree(runs, manifest["run_files"]) == []
    (runs / "raw.jsonl").write_text('{"ok":false}\n')
    (runs / "extra").write_text("unexpected")
    errors = custody.verify_tree(runs, manifest["run_files"])
    assert any("mismatch" in error for error in errors)
    assert any("unexpected" in error for error in errors)


def test_manifest_includes_rejected_attempts(tmp_path: Path) -> None:
    suite, runs, rejected = (
        tmp_path / "suite",
        tmp_path / "runs",
        tmp_path / "rejected",
    )
    suite.mkdir()
    runs.mkdir()
    rejected.mkdir()
    (suite / "suite.json").write_text("{}")
    (runs / "valid.jsonl").write_text("{}\n")
    (rejected / "REJECTION.json").write_text("{}\n")
    manifest = custody.build(suite, runs, rejected)
    assert manifest["rejected_file_count"] == 1
    assert manifest["rejected_files"][0]["path"] == "REJECTION.json"


def test_manifest_includes_derived_reports(tmp_path: Path) -> None:
    suite, runs, reports = tmp_path / "suite", tmp_path / "runs", tmp_path / "reports"
    suite.mkdir()
    runs.mkdir()
    reports.mkdir()
    (suite / "suite.json").write_text("{}")
    (runs / "valid.jsonl").write_text("{}\n")
    (reports / "verdict.json").write_text('{"verdict":"stop"}\n')
    manifest = custody.build(suite, runs, report_root=reports)
    assert manifest["report_file_count"] == 1
    assert custody.verify_tree(reports, manifest["report_files"]) == []
