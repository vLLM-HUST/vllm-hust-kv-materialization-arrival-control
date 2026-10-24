import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_raw_screen_links():
    config = json.loads((ROOT / "BENCHMARK_DOCUMENTS.json").read_text())
    document = (ROOT / "docs/SCHOOL028-RECOMPUTE-EXPERIMENT.md").read_text()
    assert len(config["raw_files"]) == 2
    for row in config["raw_files"]:
        assert row["url"] in document
        assert len(row["sha256"]) == 64
    assert "not selected as B1" in document
    assert "quality was not rescored" in document


def test_remote_screen_bytes():
    if os.environ.get("VERIFY_SCHOOL_SCREEN") != "1":
        pytest.skip("Actual downloads run in custody CI")
    config = json.loads((ROOT / "BENCHMARK_DOCUMENTS.json").read_text())
    for row in config["raw_files"]:
        assert row["url"].startswith(
            "https://raw.githubusercontent.com/vLLM-HUST/vllm-hust-benchmark/"
        )
        with urlopen(row["url"], timeout=60) as response:
            raw = response.read(row["bytes"] + 1)
        assert len(raw) == row["bytes"]
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        if row["url"].endswith(".json"):
            summary = json.loads(raw)
            assert summary["selected_as_b1"] is False
            assert summary["quality_rescored"] is False
