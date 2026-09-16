from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

from vllm_hust_ext.manifest import load_manifest

import vllm_kv_materialization
from vllm_kv_materialization.plugin import EXTENSION_ID, PLUGIN_NAME

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


ROOT = Path(__file__).parents[1]
MANIFEST = Path(vllm_kv_materialization.__file__).with_name(
    "vllm-hust-extension-v0.2.json"
)


def test_manifest_matches_package_registration() -> None:
    manifest = load_manifest(MANIFEST)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    registrations = project["entry-points"]

    assert manifest.bundle_id == EXTENSION_ID
    assert manifest.bundle_version == project["version"]
    assert manifest.kind == "in_process_plugin"
    assert manifest.lifecycle_owner == "vllm"
    assert registrations["vllm_hust.extension_bundles"][EXTENSION_ID] == (
        "vllm_kv_materialization"
    )
    assert registrations["vllm.general_plugins"][PLUGIN_NAME] == (
        "vllm_kv_materialization.plugin:register_plugin"
    )
    installed = entry_points(group="vllm_hust.extension_bundles")
    assert any(
        item.name == EXTENSION_ID and item.value == "vllm_kv_materialization"
        for item in installed
    )


def test_manifest_declares_fail_closed_host_contract() -> None:
    manifest = load_manifest(MANIFEST)

    assert manifest.runtime.process_scope == "vllm-processes"
    assert manifest.runtime.isolation == "trusted_in_process"
    assert [protocol.name for protocol in manifest.protocols] == [
        "vllm.request-processing-hook",
        "vllm.kv-materialization-runtime-control",
    ]
    assert all(
        str(protocol.version_range) == ">=1,<2" for protocol in manifest.protocols
    )
    assert manifest.requires_services == ()
    assert manifest.components[0].permissions == ("filesystem_write",)


def test_package_import_does_not_load_experiment_dependencies() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(vllm_kv_materialization.__file__).parents[1])
    code = (
        "import sys; import vllm_kv_materialization; "
        "print(int('llm_serving_workloads' in sys.modules))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.stdout.strip() == "0"
