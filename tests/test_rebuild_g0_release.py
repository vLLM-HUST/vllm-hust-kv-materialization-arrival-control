import importlib.util
import io
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "g0_release", ROOT / "scripts" / "rebuild_g0_release.py"
)
release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release)


def test_canonical_benchmark_source_preserves_original_digest() -> None:
    assert "vLLM-HUST/vllm-hust-benchmark/" in release.ARCHIVE_URL
    assert release.ASSET_API_URL.endswith("/662133494")
    assert release.EXPECTED_SHA256[release.ARCHIVE_NAME] == (
        "6474d718f65aeee3824e25897934922672c2a51e92f6c218be6f5b16a7f0ad4a"
    )


def test_portable_report_removes_only_location_fields() -> None:
    report = {
        "verdict": "stop",
        "run_root": "/producer/runs",
        "runs": [
            {
                "run_dir": "/producer/runs/001",
                "artifacts": {"raw": {"path": "/producer/raw", "sha256": "abc"}},
            }
        ],
    }
    assert release.portable_report(report) == {
        "verdict": "stop",
        "runs": [{"artifacts": {"raw": {"sha256": "abc"}}}],
    }


def test_safe_extract_rejects_parent_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        info = tarfile.TarInfo("../escape")
        payload = b"unsafe"
        info.size = len(payload)
        bundle.addfile(info, io.BytesIO(payload))
    destination = tmp_path / "output"
    destination.mkdir()
    try:
        release.safe_extract(archive, destination)
    except ValueError as exc:
        assert "escapes destination" in str(exc)
    else:
        raise AssertionError("unsafe archive traversal was accepted")
