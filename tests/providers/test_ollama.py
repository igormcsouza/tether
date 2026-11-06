"""Unit tests for tether/providers/ollama.py (Ollama /api/chat adapter & connection pooling)."""

from __future__ import annotations

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
    from tether.providers.ollama import THINK_BUDGET

    assert 2048 <= THINK_BUDGET <= 4096
    sent = await _sent_payload({"num_ctx": 8192}, "x" * 400)
    assert sent["options"]["num_predict"] == THINK_BUDGET
    # no budget when thinking is off (little room left, or the caller turned it off)
    full = await _sent_payload({"num_ctx": 8192}, "x" * 4 * 5200)
    assert "num_predict" not in full["options"]
    off = await _sent_payload({"params": {"think": False}}, "x")
    assert "num_predict" not in off["options"]
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
