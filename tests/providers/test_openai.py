"""Unit tests for tether/providers/openai.py (OpenAI-compatible /v1/chat/completions adapter)."""

from __future__ import annotations

import httpx

from tether.providers.openai import OpenAIProvider


async def test_openai_provider() -> None:
    """Verify OpenAIProvider auth header, tool call parsing, fallback extraction, and pooling."""
    oai_calls = 0

    def openai_handler(request: httpx.Request) -> httpx.Response:
        nonlocal oai_calls
        oai_calls += 1
        assert request.headers.get("Authorization") == "Bearer test-key"
        if oai_calls == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "act",
                                            "arguments": '{"cmd": "done", "stdin": "oai"}',
                                        }
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 77, "completion_tokens": 23},
                },
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": 'act("done", stdin="fallback")'}}]},
        )

    oai_client = httpx.AsyncClient(transport=httpx.MockTransport(openai_handler))
    oai = OpenAIProvider("gpt-4o-mini", api_key="test-key", client=oai_client)
    assert oai._get_client() is oai_client
    or1 = await oai.generate([{"role": "user", "content": "hi"}], [])
    assert or1.action is not None and or1.action.stdin == "oai"
    assert or1.prompt_tokens == 77
    assert or1.completion_tokens == 23
    or2 = await oai.generate([{"role": "user", "content": "hi"}], [])
    assert or2.action is not None and or2.action.stdin == "fallback"
    await oai.aclose()
    c_new = oai._get_client()
    assert not c_new.is_closed
    await oai.aclose()
