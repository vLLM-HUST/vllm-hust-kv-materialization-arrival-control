#!/usr/bin/env python3
"""Download, verify, and rebuild the immutable Issue #17 G0 custody release."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


RELEASE_TAG = "g0-issue17-stop-20260901-v2"
ARCHIVE_NAME = "g0-formal-stop-v2.tar.gz"
ARCHIVE_URL = (
    "https://github.com/intellistream/kv-materialization-arrival-control/"
    f"releases/download/{RELEASE_TAG}/{ARCHIVE_NAME}"
)
ASSET_API_URL = (
    "https://api.github.com/repos/intellistream/kv-materialization-arrival-control/"
    "releases/assets/539131048"
)
EXPECTED_SHA256 = {
    ARCHIVE_NAME: "6474d718f65aeee3824e25897934922672c2a51e92f6c218be6f5b16a7f0ad4a",
    "g0_formal_report.md": "7ee0c26105d57c1ff3f7bfd2ca0cccae715791257b9e255a2b88c32a54d4f597",
    "g0_pathology.csv": "8b7153120900fb485d7687c4cac7b830feec2ee54fe5084e1c77cff4ffd23d51",
    "g0_pathology.svg": "0c25aa7bc5c21e161c6433b636203f5894cb5c9b2230c2fb58087ace0a9685c6",
}


def load_repo_script(name: str, filename: str) -> Any:
    path = Path(__file__).resolve().with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"unsafe archive member type: {member.name}")
            target = (destination / member.name).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise ValueError(f"archive path escapes destination: {member.name}") from exc
        if "filter" in inspect.signature(bundle.extractall).parameters:
            bundle.extractall(destination, filter="fully_trusted")
        else:  # Python 3.10 compatibility after the explicit checks above.
            bundle.extractall(destination)


def portable_report(value: Any) -> Any:
    """Remove producer/extractor paths before comparing rebuilt report values."""
    if isinstance(value, dict):
        return {
            key: portable_report(item)
            for key, item in value.items()
            if key not in {"path", "run_dir", "run_root"}
        }
    if isinstance(value, list):
        return [portable_report(item) for item in value]
    return value


def require_digest(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path.name}: {actual} != {expected}")


def download_archive(destination: Path) -> None:
    """Download a public or private Release asset without exposing credentials."""
    gh = shutil.which("gh")
    if gh is not None:
        with destination.open("wb") as sink:
            subprocess.run(
                [
                    gh,
                    "api",
                    "repos/intellistream/kv-materialization-arrival-control/"
                    "releases/assets/539131048",
                    "-H",
                    "Accept: application/octet-stream",
                ],
                check=True,
                stdout=sink,
            )
        return

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    url = ASSET_API_URL if token else ARCHIVE_URL
    headers = {"Accept": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response, destination.open("wb") as sink:
        shutil.copyfileobj(response, sink)


def prepare_output(path: str | None) -> Path:
    if path is None:
        return Path(tempfile.mkdtemp(prefix="g0-issue17-release-rebuild."))
    output = Path(path).resolve()
    output.mkdir(parents=True, exist_ok=False)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        help="Use an already downloaded archive instead of the immutable Release URL",
    )
    parser.add_argument(
        "--output-dir",
        help="New directory for the extracted custody and rebuilt outputs (default: mktemp)",
    )
    args = parser.parse_args()

    output = prepare_output(args.output_dir)
    archive = Path(args.archive).resolve() if args.archive else output / ARCHIVE_NAME
    if args.archive is None:
        download_archive(archive)
    require_digest(archive, EXPECTED_SHA256[ARCHIVE_NAME])

    extracted = output / "extracted"
    extracted.mkdir()
    safe_extract(archive, extracted)

    custody = load_repo_script("g0_custody_release", "build_g0_raw_manifest.py")
    formal = load_repo_script("g0_formal_release", "rebuild_g0_formal.py")
    suite = extracted / "suite/formal_v1_20260831"
    runs = extracted / "formal_v1_20260831"
    rejected = extracted / "rejected/formal_v1_20260831"
    published = extracted / "reports/formal_v1_20260831"
    manifest_path = extracted / "custody/formal_v1_20260831/raw_manifest_v2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = custody.verify_manifest(
        manifest,
        suite_root=suite,
        run_root=runs,
        rejected_root=rejected,
        report_root=published,
    )
    if errors:
        raise ValueError("relocated custody verification failed:\n" + "\n".join(errors))

    report = formal.rebuild(suite, runs)
    if report["status"] != "complete_early_stop" or report["verdict"] != "stop":
        raise ValueError(f"unexpected rebuilt verdict: {report['status']} / {report['verdict']}")
    if report["errors"]:
        raise ValueError(f"rebuilt report contains errors: {report['errors']}")

    rebuilt = output / "rebuilt"
    rebuilt.mkdir()
    json_path = rebuilt / "g0_formal_report.json"
    markdown_path = rebuilt / "g0_formal_report.md"
    csv_path = rebuilt / "g0_pathology.csv"
    svg_path = rebuilt / "g0_pathology.svg"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(formal.markdown(report), encoding="utf-8")
    rows = formal.pathology_rows(report)
    formal.write_pathology_csv(rows, csv_path)
    formal.write_pathology_svg(rows, svg_path)

    for path in (markdown_path, csv_path, svg_path):
        require_digest(path, EXPECTED_SHA256[path.name])
    published_report = json.loads(
        (published / "g0_formal_report.json").read_text(encoding="utf-8")
    )
    if portable_report(report) != portable_report(published_report):
        raise ValueError("path-independent rebuilt JSON differs from the published report")

    summary = {
        "archive_sha256": EXPECTED_SHA256[ARCHIVE_NAME],
        "custody_files_verified": {
            "suite": manifest["suite_file_count"],
            "canonical_runs": manifest["run_file_count"],
            "rejected": manifest["rejected_file_count"],
            "reports": manifest["report_file_count"],
        },
        "executed_runs": len(report["executed_sequences"]),
        "output_dir": str(output),
        "path_independent_json_match": True,
        "published_artifact_hashes_match": True,
        "status": report["status"],
        "stop_triggers": report["stop_triggers"],
        "verdict": report["verdict"],
    }
    (rebuilt / "verification_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
