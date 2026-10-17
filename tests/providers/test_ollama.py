"""Unit tests for tether/providers/ollama.py (Ollama /api/chat adapter & connection pooling)."""

from __future__ import annotations

import httpx

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
    op = OllamaProvider("missing:model", client=client_ollama)
    r1 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert op.model_name == "qwen3.5:9b"
    assert r1.action is not None and r1.action.cmd == "done 'ok'"
    assert r1.prompt_tokens == 60

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
