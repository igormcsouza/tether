# H1: the final-answer turn when a session runs out of steps or is handed back stuck.
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, tool

FINAL = "[FINAL ANSWER]"
STUCK = "[STUCK: out of steps"


def _act(cmd: str, stdin: str | None = None) -> ModelResponse:
    return ModelResponse(
        content="", action=ActionCall(cmd=cmd, stdin=stdin), prompt_tokens=10, completion_tokens=5
    )


def _text(content: str) -> ModelResponse:
    return ModelResponse(content=content, action=None, prompt_tokens=10, completion_tokens=7)


def _three() -> list[ModelResponse]:
    return [_act("ping a.com"), _act("ping b.com"), _act("ping c.com")]


class _Provider(FakeScriptedProvider):
    # Steps come from `steps` (or `cycle`); the final-answer call is the one that sees FINAL.

    def __init__(
        self,
        steps: list[ModelResponse],
        final: ModelResponse,
        *,
        fail_final: bool = False,
        cycle: list[str] | None = None,
    ) -> None:
        super().__init__(steps)
        self.final = final
        self.fail_final = fail_final
        self.cycle = cycle
        self.final_calls = 0
        self.tools_seen: list[Any] = []

    async def generate(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse:
        self.recorded_calls.append(list(messages))
        self.tools_seen.append(tools)
        if any(FINAL in str(m.get("content") or "") for m in messages):
            self.final_calls += 1
            if self.fail_final:
                raise RuntimeError("provider down")
            return self.final
        if self.cycle:
            return _act(self.cycle[len(self.recorded_calls) % len(self.cycle)])
        if self._responses:
            return self._responses.pop(0)
        return _act("done", "Default completion")


async def _run(
    tmp_path: Path, provider: _Provider, max_steps: int = 3, verify: str | None = None
) -> tuple[Any, list[str]]:
    calls: list[str] = []

    @tool(name="ping", description="Ping a host")
    def ping(host: str) -> str:
        calls.append(host)
        return "pong"

    extra: dict[str, Any] = {"verify": verify} if verify else {}
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=[ping],
        provider=provider,
        max_steps=max_steps,
        **extra,
    )
    rec = harness.create_session("goal")
    return await harness.execute_session(rec.id), calls


async def test_plain_text_answer_leads_the_stuck_result(tmp_path: Path) -> None:
    provider = _Provider(_three(), _text("Found the bug in f.py"))
    session, calls = await _run(tmp_path, provider)
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith("Found the bug in f.py\n\n" + STUCK)
    assert calls == ["a.com", "b.com", "c.com"]
    assert provider.final_calls == 1 and len(provider.recorded_calls) == 4
    assert session.step_count <= 3


async def test_final_reply_command_is_not_executed(tmp_path: Path) -> None:
    provider = _Provider(_three(), _act("ping z.com"))
    _, calls = await _run(tmp_path, provider)
    assert calls == ["a.com", "b.com", "c.com"]


async def test_final_call_uses_the_same_tools(tmp_path: Path) -> None:
    provider = _Provider(_three(), _text("ok"))
    await _run(tmp_path, provider)
    assert len(provider.tools_seen) == 4
    assert all(t == provider.tools_seen[0] for t in provider.tools_seen)


async def test_done_stdin_is_the_answer_and_waits(tmp_path: Path) -> None:
    session, _ = await _run(tmp_path, _Provider(_three(), _act("done", "All fixed")))
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith("All fixed\n\n" + STUCK)


async def test_done_text_is_the_answer_and_waits(tmp_path: Path) -> None:
    session, _ = await _run(tmp_path, _Provider(_three(), _act("done 'All fixed'")))
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith("All fixed\n\n" + STUCK)


async def test_command_reply_is_not_an_answer_and_is_asked_once_more(tmp_path: Path) -> None:
    provider = _Provider(_three(), _act("ping z.com", "Partial work"))
    session, calls = await _run(tmp_path, provider)
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith(STUCK)
    assert provider.final_calls == 2 and calls == ["a.com", "b.com", "c.com"]


@pytest.mark.parametrize("reply", [_text("  \n"), _text("")])
async def test_empty_answer_counts_as_none(tmp_path: Path, reply: ModelResponse) -> None:
    session, _ = await _run(tmp_path, _Provider(_three(), reply))
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith(STUCK)


async def test_done_answer_with_verify_gates_stays_waiting(tmp_path: Path) -> None:
    # A failing gate, so the session is not finished by the harness before the final answer
    session, _ = await _run(tmp_path, _Provider(_three(), _act("done", "x")), verify="false")
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith("x\n\n" + STUCK)


async def test_provider_failure_in_the_final_call_ends_as_today(tmp_path: Path) -> None:
    provider = _Provider(_three(), _text("never"), fail_final=True)
    session, _ = await _run(tmp_path, provider)
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith(STUCK)
    assert provider.final_calls == 1


async def test_long_answer_is_cut_to_kept_reply_chars(tmp_path: Path) -> None:
    session, _ = await _run(tmp_path, _Provider(_three(), _text("x" * 3000)))
    result = session.result or ""
    assert result.startswith("x" * 2000) and not result.startswith("x" * 2001)


async def test_handback_gives_the_final_answer_first(tmp_path: Path) -> None:
    cycle = ["ping a.com", "ping b.com", "ping c.com"]
    provider = _Provider([], _text("Stuck answer"), cycle=cycle)
    session, _ = await _run(tmp_path, provider, max_steps=60)
    assert session.status == "WAITING_INPUT"
    assert (session.result or "").startswith("Stuck answer\n\n")
    assert provider.final_calls == 1
