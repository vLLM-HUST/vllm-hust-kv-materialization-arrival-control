from vllm_kv_materialization.live_control import (
    bind_request_headers,
    reset_request_headers,
)
from vllm_kv_materialization.school_vllm_028 import controlled_prompt
import pytest


def test_unanchored_controller_changes_only_cache_namespace(monkeypatch):
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "controller")
    token = bind_request_headers({})
    try:
        prompt = {"type": "token", "prompt_token_ids": [1, 2, 3]}
        a = controlled_prompt(prompt, "a", 256)
        b = controlled_prompt(prompt, "b", 256)
        assert prompt == {"type": "token", "prompt_token_ids": [1, 2, 3]}
        assert (
            a["prompt_token_ids"] == b["prompt_token_ids"] == prompt["prompt_token_ids"]
        )
        assert a["cache_salt"] != b["cache_salt"]
        assert a["cache_salt"].startswith("kvmat:recompute:")
    finally:
        reset_request_headers(token)


def test_non_recompute_is_not_silently_accepted(monkeypatch):
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "always_full_reuse")
    token = bind_request_headers({})
    try:
        with pytest.raises(ValueError, match="only qualifies"):
            controlled_prompt({"prompt_token_ids": [1, 2]}, "a", 256)
    finally:
        reset_request_headers(token)


def test_unsupported_input_rejected():
    with pytest.raises(ValueError, match="text token"):
        controlled_prompt({"prompt": "text"}, "a", 256)


def test_source_mismatch_fails_before_installing_hooks(monkeypatch, tmp_path):
    import sys
    import types
    from vllm_kv_materialization import school_vllm_028 as adapter

    class Chat:
        pass

    class Request:
        pass

    chat_module = types.ModuleType("vllm.entrypoints.openai.chat_completion.serving")
    chat_module.OpenAIServingChat = Chat
    request_module = types.ModuleType("vllm.v1.request")
    request_module.Request = Request
    monkeypatch.setitem(sys.modules, chat_module.__name__, chat_module)
    monkeypatch.setitem(sys.modules, request_module.__name__, request_module)
    source = tmp_path / "host.py"
    source.write_text("unqualified host")
    monkeypatch.setattr(adapter.inspect, "getfile", lambda cls: str(source))
    original_init = Request.__init__
    with pytest.raises(RuntimeError, match="source does not match"):
        adapter.register_school_vllm_028_adapter()
    assert not hasattr(Chat, "_kvmat_school028")
    assert Request.__init__ is original_init
