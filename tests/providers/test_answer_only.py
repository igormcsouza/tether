"""H1c: the final-answer call asks every built-in provider for text only."""

from __future__ import annotations

import json

import httpx

from tether.providers.anthropic import AnthropicProvider
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider

ACT = [{"type": "function", "function": {"name": "act", "parameters": {"type": "object"}}}]
MSGS = [{"role": "user", "content": "x"}]


def _client(reply: dict) -> tuple[httpx.AsyncClient, list[dict]]:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_ollama_answer_only_sends_no_tools() -> None:
    client, seen = _client({"message": {"content": "ok"}, "done_reason": "stop"})
    provider = OllamaProvider("m", client=client)
    await provider.generate(MSGS, ACT, answer_only=True)
    await provider.generate(MSGS, ACT)
    assert "tools" not in seen[0] and seen[1]["tools"] == ACT


async def test_openai_answer_only_sets_tool_choice_none() -> None:
    client, seen = _client({"choices": [{"message": {"content": "ok"}}], "usage": {}})
    provider = OpenAIProvider("m", api_key="k", client=client)
    await provider.generate(MSGS, ACT, answer_only=True)
    await provider.generate(MSGS, ACT)
    assert seen[0]["tool_choice"] == "none" and seen[0]["tools"] == ACT
    assert "tool_choice" not in seen[1]


async def test_anthropic_answer_only_sets_tool_choice_none() -> None:
    client, seen = _client({"content": [{"type": "text", "text": "ok"}], "usage": {}})
    provider = AnthropicProvider("m", api_key="k", client=client)
    await provider.generate(MSGS, ACT, answer_only=True)
    await provider.generate(MSGS, ACT)
    assert seen[0]["tool_choice"] == {"type": "none"} and seen[0]["tools"]
    assert "tool_choice" not in seen[1]
