from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from tests.conftest import FakeScriptedProvider
from tether.harness import Harness
from tether.providers.base import ActionCall, ModelResponse
from tether.providers.ollama import OllamaProvider

MARKER = "[empty reply from ollama/qwen3:8b: no text and no tool call, twice]"
MSG: list[dict[str, Any]] = [{"role": "user", "content": "go"}]
EMPTY: dict[str, Any] = {
    "message": {"role": "assistant", "content": ""},
    "prompt_eval_count": 10,
    "eval_count": 2,
}
DONE: dict[str, Any] = {
    "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "act", "arguments": {"cmd": "done", "stdin": "ok"}}}],
    },
    "prompt_eval_count": 10,
    "eval_count": 2,
}


def _provider(replies: list[dict[str, Any]], bodies: list[bytes]) -> OllamaProvider:
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(200, json=queue.pop(0))

    provider = OllamaProvider("qwen3:8b")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider._get_client = lambda: client  # type: ignore[method-assign]
    return provider


async def test_ollama_empty_reply_retried_once_recovers() -> None:
    bodies: list[bytes] = []
    provider = _provider([EMPTY, DONE], bodies)
    resp = await provider.generate(MSG, [])
    assert len(bodies) == 2
    assert bodies[0] == bodies[1]
    assert resp.action is not None
    assert resp.action.cmd == "done"
    assert resp.empty is False
    assert resp.prompt_tokens == 20
    assert resp.completion_tokens == 4


async def test_ollama_empty_twice_returns_marker() -> None:
    bodies: list[bytes] = []
    provider = _provider([EMPTY, EMPTY], bodies)
    resp = await provider.generate(MSG, [])
    assert len(bodies) == 2
    assert resp.content == MARKER
    assert resp.empty is True
    assert resp.action is None
    assert resp.prompt_tokens == 20
    assert resp.completion_tokens == 4


async def test_ollama_thinking_reply_not_retried() -> None:
    bodies: list[bytes] = []
    thinking: dict[str, Any] = {
        "message": {"role": "assistant", "content": "", "thinking": "hmm"},
        "prompt_eval_count": 10,
        "eval_count": 2,
    }
    provider = _provider([thinking], bodies)
    resp = await provider.generate(MSG, [])
    assert len(bodies) == 1
    assert resp.empty is False


async def test_ollama_empty_budget_cut_not_retried() -> None:
    bodies: list[bytes] = []
    cut: dict[str, Any] = {
        "message": {"role": "assistant", "content": ""},
        "done_reason": "length",
        "prompt_eval_count": 10,
        "eval_count": 2,
    }
    provider = _provider([cut], bodies)
    provider.params = {"num_predict": 100}
    resp = await provider.generate(MSG, [])
    assert len(bodies) == 1
    assert resp.action is None


async def test_harness_stops_after_three_empty_replies(tmp_path: Path) -> None:
    provider = FakeScriptedProvider([ModelResponse(content=MARKER, empty=True) for _ in range(3)])
    provider.model_name = "ollama/qwen3:8b"
    session = await Harness(db_path=tmp_path / "tether.db", provider=provider).run("go")
    assert session.status == "WAITING_INPUT"
    assert session.result is not None
    assert "qwen3:8b" in session.result
    assert "--param think=false" in session.result
    assert len(provider.recorded_calls) == 3


async def test_harness_empty_streak_resets_on_real_reply(tmp_path: Path) -> None:
    empty = ModelResponse(content=MARKER, empty=True)
    prose = ModelResponse(content="I will think about the next step first.")
    done = ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))
    provider = FakeScriptedProvider([empty, prose, empty, empty, done])
    session = await Harness(db_path=tmp_path / "tether.db", provider=provider).run("go")
    assert session.status == "COMPLETED"


def test_model_response_empty_defaults_false() -> None:
    assert ModelResponse(content="x").empty is False
