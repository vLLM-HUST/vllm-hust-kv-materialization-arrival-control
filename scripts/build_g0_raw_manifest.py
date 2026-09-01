#!/usr/bin/env python3
"""Build or verify a complete SHA-256 manifest for a formal G0 raw suite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(base: Path, path: Path) -> dict[str, Any]:
    metadata = path.stat()
    return {
        "path": path.relative_to(base).as_posix(),
        "bytes": metadata.st_size,
        "mode": stat.S_IMODE(metadata.st_mode),
        "sha256": sha256(path),
    }


def tree(base: Path) -> list[dict[str, Any]]:
    if not base.is_dir():
        raise ValueError(f"not a directory: {base}")
    files = []
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed in raw custody: {path}")
        if path.is_file():
            files.append(record(base, path))
    return files


def build(
    suite: Path,
    run_root: Path,
    rejected_root: Path | None = None,
    report_root: Path | None = None,
) -> dict[str, Any]:
    suite_files = tree(suite)
    run_files = tree(run_root)
    rejected_files = tree(rejected_root) if rejected_root is not None else []
    report_files = tree(report_root) if report_root is not None else []
    return {
        "schema_version": 1,
        "artifact": "g0-formal-complete-raw-manifest",
        "custodian": os.environ.get("USER", "unknown"),
        "suite_root": str(suite.resolve()),
        "run_root": str(run_root.resolve()),
        "rejected_root": str(rejected_root.resolve()) if rejected_root is not None else None,
        "report_root": str(report_root.resolve()) if report_root is not None else None,
        "suite_files": suite_files,
        "run_files": run_files,
        "rejected_files": rejected_files,
        "report_files": report_files,
        "suite_file_count": len(suite_files),
        "run_file_count": len(run_files),
        "rejected_file_count": len(rejected_files),
        "report_file_count": len(report_files),
        "suite_bytes": sum(row["bytes"] for row in suite_files),
        "run_bytes": sum(row["bytes"] for row in run_files),
        "rejected_bytes": sum(row["bytes"] for row in rejected_files),
        "report_bytes": sum(row["bytes"] for row in report_files),
    }


def verify_tree(root: Path, expected: list[dict[str, Any]]) -> list[str]:
    errors = []
    current_paths = {row["path"] for row in tree(root)}
    expected_paths = {row["path"] for row in expected}
    for missing in sorted(expected_paths - current_paths):
        errors.append(f"missing: {root / missing}")
    for extra in sorted(current_paths - expected_paths):
        errors.append(f"unexpected: {root / extra}")
    for row in expected:
        path = root / row["path"]
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size != row["bytes"]:
            errors.append(f"size mismatch: {path}: {size} != {row['bytes']}")
            continue
        digest = sha256(path)
        if digest != row["sha256"]:
            errors.append(f"sha256 mismatch: {path}: {digest} != {row['sha256']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--suite-dir", required=True)
    build_parser.add_argument("--run-root", required=True)
    build_parser.add_argument("--rejected-root")
    build_parser.add_argument("--report-root")
    build_parser.add_argument("--output", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    if args.command == "build":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest = build(
            Path(args.suite_dir).resolve(),
            Path(args.run_root).resolve(),
            Path(args.rejected_root).resolve() if args.rejected_root else None,
            Path(args.report_root).resolve() if args.report_root else None,
        )
        output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    errors = verify_tree(Path(manifest["suite_root"]), manifest["suite_files"])
    errors.extend(verify_tree(Path(manifest["run_root"]), manifest["run_files"]))
    if manifest.get("rejected_root"):
        errors.extend(
            verify_tree(Path(manifest["rejected_root"]), manifest["rejected_files"])
        )
    if manifest.get("report_root"):
        errors.extend(verify_tree(Path(manifest["report_root"]), manifest["report_files"]))
    if errors:
        for error in errors:
            print(error)
        return 1
    print(
        f"verified suite_files={manifest['suite_file_count']} "
        f"run_files={manifest['run_file_count']} "
        f"rejected_files={manifest.get('rejected_file_count', 0)}"
        f" report_files={manifest.get('report_file_count', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
