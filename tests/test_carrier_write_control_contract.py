from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "carrier/vllm-hust/vllm/v1/core"


def _parser_module():
    spec = importlib.util.spec_from_file_location(
        "kvplane_write_control", CORE / "kvplane_write_control.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_control_parser_is_closed_and_malformed_values_deny() -> None:
    allowed = _parser_module().allows_prefix_cache_write
    assert allowed(None) is True
    assert allowed(True) is True
    assert allowed("admit") is True
    assert allowed(False) is False
    assert allowed("deny") is False
    assert allowed("unexpected") is False
    assert allowed(1) is False


def test_carrier_places_deny_checks_on_all_write_and_free_paths() -> None:
    source = (CORE / "kv_cache_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    allocate = functions["allocate_slots"]
    cache = functions["cache_blocks"]
    free = functions["free"]
    assert "_kvplane_denies_prefix_cache_write(request)" in allocate
    assert "return self.create_kv_cache_blocks(new_blocks)" in allocate
    assert "_kvplane_denies_prefix_cache_write(request)" in cache
    assert "return" in cache
    assert "prioritize_uncached_for_reuse=_kvplane_denies_prefix_cache_write(request)" in free
