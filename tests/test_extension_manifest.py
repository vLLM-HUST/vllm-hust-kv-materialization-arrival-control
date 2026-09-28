from __future__ import annotations

import json
from importlib.resources import files


def test_extension_manifest_activates_registered_plugin_without_machine_paths() -> None:
    path = files("vllm_kv_materialization").joinpath("vllm-hust-extension-v0.2.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["extension_id"] == (
        "org.vllm-hust.kv-materialization-arrival-control"
    )
    assert payload["host"]["provider"] == "vllm"
    assert payload["implementation"] == [
        {
            "type": "python_entry_point",
            "group": "vllm.general_plugins",
            "name": "kv_materialization",
        }
    ]
    assert payload["activation"]["entry_points"] == [
        {"group": "vllm.general_plugins", "name": "kv_materialization"}
    ]
    assert payload["activation"]["environment"] == {}
    assert [protocol["version_range"] for protocol in payload["protocols"]] == [
        ">=1,<2",
        ">=1,<2",
    ]
    encoded = json.dumps(payload)
    assert "/root/" not in encoded
    assert "/models/" not in encoded
