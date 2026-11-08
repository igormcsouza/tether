"""Model `thinking` text is surfaced by `tether events` only when present."""

from __future__ import annotations

from typing import Any

from tether import api
from tether.store import TurnRecord


class _Store:
    def __init__(self, turns: list[TurnRecord]) -> None:
        self._turns = turns

    def get_turns(self, session_id: str) -> list[TurnRecord]:
        return self._turns


def _turn(tid: int, thinking: str) -> TurnRecord:
    return TurnRecord(
        id=tid,
        session_id="s",
        step=tid,
        role="assistant",
        content="hi",
        tool_cmd="bash",
        tool_stdin=None,
        obs_id=None,
        created_at=0.0,
        thinking=thinking,
    )


def test_events_includes_thinking_only_when_present() -> None:
    store: Any = _Store([_turn(1, "reasoning"), _turn(2, "")])
    out = api.events(store, "s")
    assert out[0]["thinking"] == "reasoning"
    assert "thinking" not in out[1]
