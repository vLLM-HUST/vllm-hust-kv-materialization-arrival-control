import hashlib
import json
import re
from pathlib import Path


PAPER_ROOT = Path(__file__).resolve().parents[1] / "paper" / "kv_materialization_control"


def test_manuscript_inputs_are_present_and_content_addressed():
    metadata = json.loads((PAPER_ROOT / "PAPER_INPUTS.json").read_text())

    for item in metadata["manuscript_inputs"]:
        path = PAPER_ROOT / item["path"]
        assert path.is_file(), item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_latex_inputs_exist_in_fresh_checkout():
    manuscript = (PAPER_ROOT / "kv_materialization_control.tex").read_text()

    for relative_path in re.findall(r"\\input\{([^}]+)\}", manuscript):
        assert (PAPER_ROOT / relative_path).is_file(), relative_path
