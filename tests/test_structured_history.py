"""Structured tool-call history replay (#38): assembler shape, trimming, provider payloads."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tether.context import ContextAssembler
from tether.providers.anthropic import AnthropicProvider
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider
from tether.store import TurnRecord


def _history() -> list[TurnRecord]:
    big = "x" * 1000
    return [
        TurnRecord(1, "s", 1, "assistant", "", "edit write f.py", big, None, 0.0),
        TurnRecord(2, "s", 1, "tool", "ok", None, None, None, 0.0),
        TurnRecord(3, "s", 2, "assistant", "", "bash ls", None, None, 0.0),
        TurnRecord(4, "s", 2, "tool", "f.py", None, None, None, 0.0),
        TurnRecord(5, "s", 3, "assistant", "hmm", "bash pwd", None, None, 0.0),
    ]


def _assemble(
    structured: bool,
    turns: list[TurnRecord],
    pins: dict[str, str] | None = None,
    max_context_tokens: int = 8192,
) -> list[dict[str, Any]]:
    ca = ContextAssembler(structured=structured, max_context_tokens=max_context_tokens)
    return ca.assemble(
        system_prompt="Sys",
        goal="G",
        turns=turns,
        observations={},
        pins=pins or {},
        current_step=4,
    )


def test_structured_history_shape_and_no_text_form() -> None:
    msgs = _assemble(True, _history())
    call, result = msgs[2], msgs[3]
    assert call["role"] == "assistant" and call["content"] == ""
    tc = call["tool_calls"][0]
    assert tc["function"]["name"] == "act" and tc["id"] == "call_1"
    args = tc["function"]["arguments"]
    assert args["cmd"] == "edit write f.py"
    # real bounded prefix, never a copyable `<N chars>` placeholder
    assert args["stdin"] == "x" * 400 + "…"
    assert result == {"role": "tool", "tool_call_id": "call_1", "content": "ok"}
    # trailing action with no result stays textual (no dangling tool_call)
    assert msgs[-1]["role"] == "assistant" and "tool_calls" not in msgs[-1]
    dumped = "".join(m["content"] for m in msgs[2:-1])
    assert "act(" not in dumped and "chars>" not in dumped


def test_textual_fallback_keeps_old_form() -> None:
    msgs = _assemble(False, _history())
    assert msgs[2] == {"role": "assistant", "content": "act('edit write f.py', stdin=<1000 chars>)"}
    assert msgs[3] == {"role": "user", "content": "Observation:\nok"}
    assert not any("tool_calls" in m or m["role"] == "tool" for m in msgs)


def test_structured_orphan_tool_and_pin_after_tool() -> None:
    orphan = [TurnRecord(1, "s", 1, "tool", "digest", None, None, None, 0.0)]
    assert _assemble(True, orphan)[-1] == {"role": "user", "content": "Observation:\ndigest"}
    msgs = _assemble(True, _history()[:2], pins={"k": "v"})
    assert msgs[-2]["role"] == "tool"
    assert msgs[-1]["role"] == "user" and "[PINNED MEMORY]" in msgs[-1]["content"]


def test_structured_trimming_never_splits_call_from_result() -> None:
    turns: list[TurnRecord] = []
    for i in range(10):
        turns.append(TurnRecord(2 * i, "s", i, "assistant", "", f"bash c{i}", None, None, 0.0))
        turns.append(TurnRecord(2 * i + 1, "s", i, "tool", "out " * 50, None, None, None, 0.0))
    hist = _assemble(True, turns, max_context_tokens=400)[2:]
    assert 0 < len(hist) < 20 and len(hist) % 2 == 0
    for call, res in zip(hist[::2], hist[1::2], strict=True):
        assert call["tool_calls"][0]["id"] == res["tool_call_id"]


_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "act", "arguments": {"cmd": "ls"}},
}
_MSGS: list[dict[str, Any]] = [
    {"role": "system", "content": "S"},
    {"role": "user", "content": "Goal"},
    {"role": "assistant", "content": "thinking", "tool_calls": [_CALL]},
    {"role": "tool", "tool_call_id": "call_1", "content": "out"},
    {"role": "user", "content": "[PINNED MEMORY]"},
]


async def _payload(provider_cls: Any, response: dict[str, Any], **kw: Any) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=response)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = provider_cls("m", client=client, **kw)
    assert provider.structured_history is True
    await provider.generate(_MSGS, [])
    return seen


async def test_ollama_payload_keeps_native_tool_messages() -> None:
    seen = await _payload(OllamaProvider, {"message": {"content": "hi"}})
    assert seen["messages"][2]["tool_calls"][0]["function"]["arguments"] == {"cmd": "ls"}
    assert seen["messages"][3]["role"] == "tool" and seen["messages"][3]["tool_name"] == "act"


async def test_openai_payload_stringifies_arguments() -> None:
    seen = await _payload(
        OpenAIProvider, {"choices": [{"message": {"content": "hi"}}]}, api_key="k"
    )
    tc = seen["messages"][2]["tool_calls"][0]
    assert tc["id"] == "call_1" and json.loads(tc["function"]["arguments"]) == {"cmd": "ls"}
    assert seen["messages"][3]["tool_call_id"] == "call_1"
    assert seen["messages"][1] == {"role": "user", "content": "Goal"}


async def test_anthropic_payload_uses_tool_use_and_tool_result_blocks() -> None:
    seen = await _payload(
        AnthropicProvider, {"content": [{"type": "text", "text": "hi"}]}, api_key="k"
    )
    m = seen["messages"]
    assert [x["role"] for x in m] == ["user", "assistant", "user"]
    assert m[1]["content"] == [
        {"type": "text", "text": "thinking"},
        {"type": "tool_use", "id": "call_1", "name": "act", "input": {"cmd": "ls"}},
    ]
    # tool_result must lead its user turn; the trailing user text merges after it
    assert m[2]["content"][0] == {"type": "tool_result", "tool_use_id": "call_1", "content": "out"}
    assert m[2]["content"][1]["text"] == "[PINNED MEMORY]"


async def test_anthropic_tool_use_without_text_block() -> None:
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [_CALL]},
        {"role": "tool", "tool_call_id": "call_1", "content": ""},
    ]
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"content": []})

    p = AnthropicProvider(
        "m", api_key="k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await p.generate(msgs, [])
    assert seen["messages"][0]["content"][0]["type"] == "tool_use"
    assert seen["messages"][1]["content"][0]["content"] == "(empty)"
