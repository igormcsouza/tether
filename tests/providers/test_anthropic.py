"""Unit tests for tether/providers/anthropic.py (Anthropic /v1/messages & ephemeral caching)."""

from __future__ import annotations

import json

import httpx

from tether.providers.anthropic import AnthropicProvider


async def test_anthropic_provider_and_ephemeral_cache() -> None:
    """Verify AnthropicProvider message coalescing, ephemeral cache, and tool_use parsing."""
    anth_calls = 0

    def anthropic_handler(request: httpx.Request) -> httpx.Response:
        nonlocal anth_calls
        anth_calls += 1
        assert request.headers.get("anthropic-workspace-id") == "ws_123"
        payload = json.loads(request.content.decode("utf-8"))
        if anth_calls == 1:
            assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}
            assert payload["tools"][-1]["cache_control"] == {"type": "ephemeral"}
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "Thinking..."},
                        {"type": "tool_use", "input": {"cmd": "done", "stdin": "claude_ok"}},
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 25},
                },
            )
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": 'act("done", stdin="anth_fb")'}]},
        )

    anth_client = httpx.AsyncClient(transport=httpx.MockTransport(anthropic_handler))
    anth = AnthropicProvider(
        "claude-3-7-sonnet-latest",
        api_key="ak",
        workspace_id="ws_123",
        client=anth_client,
    )
    ar1 = await anth.generate(
        [
            {"role": "system", "content": "Sys"},
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
        ],
        [{"function": {"name": "act", "description": "d", "parameters": {}}}],
    )
    assert ar1.action is not None and ar1.action.stdin == "claude_ok"
    assert ar1.prompt_tokens == 125
    ar2 = await anth.generate([{"role": "user", "content": "Hi"}], [])
    assert ar2.action is not None and ar2.action.stdin == "anth_fb"
    await anth.aclose()
    c_anth_new = anth._get_client()
    assert not c_anth_new.is_closed
    await anth.aclose()
