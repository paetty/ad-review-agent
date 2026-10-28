import asyncio
import json

import httpx
import pytest

from app.provider import OpenAICompatibleProvider, ProviderError


@pytest.mark.parametrize("option,expected", [(None, None), ("false", False), ("true", True)])
def test_thinking_option_is_explicit_and_optional(monkeypatch, option, expected):
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    if option is None:
        monkeypatch.delenv("LLM_ENABLE_THINKING", raising=False)
    else:
        monkeypatch.setenv("LLM_ENABLE_THINKING", option)
    captured = {}

    async def fake_post(self, url, *, headers, json):
        captured.update(json)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(OpenAICompatibleProvider().generate([], {"type": "object"}))
    assert result.data == {"ok": True}
    assert result.input_tokens == 8 and result.output_tokens == 4
    assert captured["response_format"]["type"] == "json_schema"
    if expected is None:
        assert "enable_thinking" not in captured
    else:
        assert captured["enable_thinking"] is expected


def test_invalid_thinking_option_rejected_before_network(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_ENABLE_THINKING", "invalid")
    with pytest.raises(ProviderError, match="LLM_ENABLE_THINKING"):
        asyncio.run(OpenAICompatibleProvider().generate([], {}))
