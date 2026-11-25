"""Unit tests for tether/providers/ollama.py (Ollama /api/chat adapter & connection pooling)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from tether.providers.ollama import OllamaProvider


async def test_ollama_provider_and_connection_pooling() -> None:
    """Verify OllamaProvider HTTP transport, 404 model fallback, tool calls, and client reuse."""
    provider = OllamaProvider("qwen3.5:9b")
    c1 = provider._get_client()
    c2 = provider._get_client()
    assert c1 is c2
    await provider.aclose()
    assert c1.is_closed

    ollama_step = 0

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        nonlocal ollama_step
        if request.url.path == "/api/tags":
            if ollama_step == 1:
                return httpx.Response(
                    200, json={"models": [{"name": "gemma4:e4b"}, {"name": "qwen3.5:9b"}]}
                )
            if ollama_step == 2:
                return httpx.Response(200, json={"models": [{"name": "gemma4:e4b"}]})
            if ollama_step == 3:
                return httpx.Response(200, json={"models": []})
            return httpx.Response(500)

        ollama_step += 1
        if ollama_step == 1:
            return httpx.Response(404)
        if ollama_step == 2:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "act", "arguments": {"cmd": "done 'ok'"}}}
                        ],
                    },
                    "prompt_eval_count": 50,
                    "eval_count": 10,
                },
            )
        if ollama_step == 3:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "web", "arguments": {"q": "ai"}}}],
                    }
                },
            )
        if ollama_step == 4:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "web", "arguments": "raw"}}],
                    }
                },
            )
        return httpx.Response(
            200,
            json={"message": {"content": 'act("done", stdin="from text")'}},
        )

    client_ollama = httpx.AsyncClient(transport=httpx.MockTransport(ollama_handler))
    op = OllamaProvider("missing:model", client=client_ollama, fallback=True)
    r1 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert op.model_name == "qwen3.5:9b"
    assert r1.action is not None and r1.action.cmd == "done 'ok'"
    assert r1.prompt_tokens == 50
    assert r1.completion_tokens == 10

    ollama_step = 2
    assert await op._resolve_installed_model(client_ollama) == "gemma4:e4b"
    ollama_step = 3
    assert await op._resolve_installed_model(client_ollama) is None
    ollama_step = 4
    assert await op._resolve_installed_model(client_ollama) is None

    ollama_step = 2
    r2 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert r2.action is not None and "web --q 'ai'" in r2.action.cmd
    r3 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert r3.action is not None and r3.action.cmd == "web"
    r4 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert r4.action is not None and r4.action.stdin == "from text"
    await op.aclose()


async def test_ollama_unknown_model_fails_loudly_by_default() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    op = OllamaProvider("doesnotexist", client=client, fallback=False)
    with pytest.raises(RuntimeError, match="doesnotexist.*installed: qwen3.5:9b"):
        await op.generate([{"role": "user", "content": "hi"}], [])


def test_default_timeout_fits_a_full_window_of_thinking() -> None:
    """North star: 4/68 baseline runs died on a 120s ReadTimeout while the model was thinking."""
    from tether.providers.ollama import OllamaProvider

    assert OllamaProvider().timeout >= 300


async def _sent_payload(provider_kwargs: dict, text: str) -> dict:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"message": {"content": "hi"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("m", client=client, **provider_kwargs)
    await provider.generate([{"role": "user", "content": text}], [])
    return seen


async def test_thinking_is_off_when_little_window_is_left_for_the_reply() -> None:
    """#183: a prompt that leaves < 3072 tokens of num_ctx cannot hold a thinking reply."""
    small = await _sent_payload({"num_ctx": 8192}, "x" * 400)
    assert "think" not in small
    full = await _sent_payload({"num_ctx": 8192}, "x" * 4 * 5200)
    assert full["think"] is False
    # an explicit `think` param always wins
    forced = await _sent_payload({"num_ctx": 8192, "params": {"think": True}}, "x" * 4 * 5200)
    assert forced["think"] is True
    # headroom scales with the window: the same prompt is fine in a 32k window
    assert "think" not in await _sent_payload({"num_ctx": 32768}, "x" * 4 * 5200)


def _scripted(replies: list[dict]) -> tuple[httpx.AsyncClient, list[dict]]:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(__import__("json").loads(request.content))
        return httpx.Response(200, json=replies[min(len(seen), len(replies)) - 1])

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


_CUT = {
    "message": {"content": ""},
    "done_reason": "length",
    "eval_count": 2560,
    "prompt_eval_count": 900,
}
_CMD = {
    "message": {
        "content": "",
        "tool_calls": [{"function": {"name": "act", "arguments": {"cmd": "ls"}}}],
    },
    "done_reason": "stop",
    "eval_count": 30,
    "prompt_eval_count": 900,
}


async def test_a_thinking_turn_has_an_output_budget() -> None:
    """#173: runaway thinking filled the window and lost the turn; healthy turns use < 2.2k."""
    from tether.providers.ollama import REPLY_CEILING, THINK_BUDGET

    assert 2048 <= THINK_BUDGET <= 4096
    sent = await _sent_payload({"num_ctx": 8192}, "x" * 400)
    # thinking is capped by the stream; num_predict is only the thinking + reply ceiling (AD-29)
    assert sent["options"]["num_predict"] == REPLY_CEILING and sent["stream"] is True
    # no budget when thinking is off (little room left, or the caller turned it off)
    full = await _sent_payload({"num_ctx": 8192}, "x" * 4 * 5200)
    assert "num_predict" not in full["options"]
    assert full["stream"] is False
    off = await _sent_payload({"params": {"think": False}}, "x")
    assert "num_predict" not in off["options"] and off["stream"] is False
    # an explicit num_predict always wins
    own = await _sent_payload({"params": {"num_predict": -1}}, "x")
    assert own["options"]["num_predict"] == -1


async def test_a_turn_cut_while_thinking_is_asked_again_without_thinking() -> None:
    client, seen = _scripted([_CUT, _CMD])
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert resp.action is not None and resp.action.cmd == "ls"
    assert len(seen) == 2
    assert seen[1]["think"] is False and "num_predict" not in seen[1]["options"]
    assert seen[1]["messages"] == seen[0]["messages"]  # same turn, nothing added
    assert resp.completion_tokens == 2560 + 30 and resp.prompt_tokens == 900 + 900


async def test_no_second_ask_when_the_turn_has_a_command_or_was_not_cut() -> None:
    cut_cmd = {**_CMD, "done_reason": "length"}
    for first in (cut_cmd, {"message": {"content": "thinking out loud"}, "done_reason": "stop"}):
        client, seen = _scripted([first, _CMD])
        await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
        assert len(seen) == 1


async def test_no_second_ask_when_the_caller_set_the_budget() -> None:
    client, seen = _scripted([_CUT, _CMD])
    prov = OllamaProvider("m", client=client, params={"num_predict": 100})
    resp = await prov.generate([{"role": "user", "content": "x"}], [])
    assert len(seen) == 1 and resp.action is None


async def test_a_bad_tool_call_in_the_second_ask_becomes_a_hint() -> None:
    """#173: Ollama's 500 for a malformed tool call in the think-off ask crashed the worker."""
    from tether.providers.base import REJECTED_CALL_HINT

    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        if len(seen) == 1:
            return httpx.Response(200, json=_CUT)
        return httpx.Response(500, json={"error": "error parsing tool call: raw='<tool_call>'"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert len(seen) == 2
    assert resp.action is None and resp.hint == REJECTED_CALL_HINT


_REJECTED = {"error": "error parsing tool call: raw='<tool_call>'"}


def _replies(*replies: tuple[int, dict]) -> tuple[httpx.AsyncClient, list[dict]]:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(__import__("json").loads(request.content))
        code, body = replies[min(len(seen), len(replies)) - 1]
        return httpx.Response(code, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_a_call_cut_by_the_budget_is_asked_again_without_thinking() -> None:
    """#173: 8 of 8 rejected calls in a bench arm came at ~2560 tokens (74-78 s at 33 tok/s).

    The budget cut a whole-file write mid-call, Ollama could not parse the half call and
    answered 500; the model lost the turn and wrote the file again. Thinking off, the same
    turn fits.
    """
    client, seen = _replies((500, _REJECTED), (200, _CMD))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert resp.action is not None and resp.action.cmd == "ls" and not resp.hint
    assert len(seen) == 2
    assert seen[1]["think"] is False and "num_predict" not in seen[1]["options"]
    assert seen[1]["messages"] == seen[0]["messages"]


async def test_a_rejected_cut_call_counts_the_budget_it_was_given() -> None:
    """Ollama returns no counts on the 500, so the cut call counts its num_predict budget."""
    from tether.providers.ollama import THINK_BUDGET

    client, seen = _replies((500, _REJECTED), (200, _CMD))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert resp.action is not None and len(seen) == 2
    assert resp.completion_tokens == THINK_BUDGET + 30
    assert resp.prompt_tokens == 2 * 900  # the same prompt, evaluated by the cut call and the retry


async def test_a_rejected_call_without_the_budget_is_a_hint_at_once() -> None:
    """No budget, no cut: the call itself was malformed, the model is told to resend it."""
    from tether.providers.base import REJECTED_CALL_HINT

    for params in ({"think": False}, {"num_predict": -1}):
        client, seen = _replies((500, _REJECTED), (200, _CMD))
        prov = OllamaProvider("m", client=client, params=params)
        resp = await prov.generate([{"role": "user", "content": "x"}], [])
        assert len(seen) == 1 and resp.hint == REJECTED_CALL_HINT


async def test_a_call_rejected_twice_is_a_hint() -> None:
    from tether.providers.base import REJECTED_CALL_HINT

    client, seen = _replies((500, _REJECTED), (500, _REJECTED), (200, _CMD))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert len(seen) == 2 and resp.action is None and resp.hint == REJECTED_CALL_HINT


async def test_the_second_ask_is_asked_once() -> None:
    client, seen = _scripted([_CUT, _CUT, _CMD])
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert len(seen) == 2 and resp.action is None


def _line(chunk: dict) -> bytes:
    return json.dumps(chunk).encode() + b"\n"


def _think() -> dict:
    return {"message": {"role": "assistant", "content": "", "thinking": "t"}, "done": False}


def _text(text: str) -> dict:
    return {"message": {"role": "assistant", "content": text}, "done": False}


_LS_CALL = {
    "message": {
        "content": "",
        "tool_calls": [{"function": {"name": "act", "arguments": {"cmd": "ls"}}}],
    },
    "done": False,
}


def _done(done_reason: str, prompt: int, completion: int) -> dict:
    return {
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": done_reason,
        "prompt_eval_count": prompt,
        "eval_count": completion,
    }


class _Counted(httpx.AsyncByteStream):
    """A body that counts the lines a client actually pulled from it."""

    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines
        self.consumed = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for line in self.lines:
            self.consumed += 1
            yield line


async def test_a_streamed_turn_parses_like_the_single_body() -> None:
    """Thinking chunks, a reply, a tool call and the done line form the same turn as one body."""
    thinking = "t" * 300
    body = {
        "message": {
            "role": "assistant",
            "content": "ok",
            "thinking": thinking,
            "tool_calls": _LS_CALL["message"]["tool_calls"],
        },
        "done_reason": "stop",
        "prompt_eval_count": 900,
        "eval_count": 310,
    }
    chunks = [_line(_think()) for _ in range(300)] + [_line(_text("ok")), _line(_LS_CALL)]
    stream = b"".join(chunks) + b"\n" + _line(_done("stop", 900, 310))  # a blank line is skipped
    streamed = _client_for(httpx.Response(200, stream=httpx.ByteStream(stream)))
    single = _client_for(httpx.Response(200, json=body))
    a = await OllamaProvider("m", client=streamed[0]).generate(
        [{"role": "user", "content": "x"}], []
    )
    b = await OllamaProvider("m", client=single[0], params={"think": False}).generate(
        [{"role": "user", "content": "x"}], []
    )
    assert a == b
    assert a.thinking == thinking and a.content == "ok" and a.action is not None
    assert (a.prompt_tokens, a.completion_tokens) == (900, 310)


def _client_for(response: httpx.Response) -> tuple[httpx.AsyncClient, list[dict]]:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return response

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_a_runaway_thought_is_cut_at_the_budget_and_asked_again() -> None:
    """A thought that reaches THINK_BUDGET with no reply stops the stream there (AD-29)."""
    from tether.providers.ollama import THINK_BUDGET

    body = _Counted([_line(_think()) for _ in range(5000)])
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return (
            httpx.Response(200, stream=body) if len(seen) == 1 else httpx.Response(200, json=_CMD)
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert body.consumed < THINK_BUDGET + 50, body.consumed
    assert resp.action is not None and resp.action.cmd == "ls"
    assert len(seen) == 2
    assert seen[0]["stream"] is True and seen[1]["think"] is False and seen[1]["stream"] is False
    # the cut call counts its thinking chunks; Ollama sent no prompt count, so the prompt twice
    assert resp.completion_tokens == THINK_BUDGET + 30
    assert resp.prompt_tokens == 2 * 900


async def test_long_thinking_then_a_long_reply_is_not_cut() -> None:
    """2,000 thinking chunks end before the budget; the reply that follows is never cut."""
    lines = [_line(_think()) for _ in range(2000)] + [_line(_text("x")) for _ in range(3000)]
    lines.append(_line(_done("stop", 900, 5000)))
    client, seen = _client_for(httpx.Response(200, stream=httpx.ByteStream(b"".join(lines))))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert len(seen) == 1 and resp.content == "x" * 3000
    assert resp.completion_tokens == 5000 and resp.action is None


async def test_an_error_line_mid_stream_takes_the_rejected_call_path() -> None:
    """Ollama reports a failure after the 200 as an NDJSON error line: same as a 500 (AD-29)."""
    from tether.providers.ollama import THINK_BUDGET

    error = {"error": "error parsing tool call: raw='<tool_call>'"}
    lines = [_line(_think()) for _ in range(10)] + [_line(error)]
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(200, stream=httpx.ByteStream(b"".join(lines)))
        return httpx.Response(200, json=_CMD)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = await OllamaProvider("m", client=client).generate([{"role": "user", "content": "x"}], [])
    assert resp.action is not None and resp.action.cmd == "ls" and not resp.hint
    assert len(calls) == 2
    assert calls[1]["think"] is False and calls[1]["stream"] is False
    # rejected like the 500 path: the cut call counts its budget, as there
    assert resp.completion_tokens == THINK_BUDGET + 30
