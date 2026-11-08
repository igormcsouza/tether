"""#32 review fixes: stored thinking is capped at 4000 chars; the empty case says what to do."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import Harness
from tether.cli import _async_main


def test_thinking_is_capped_at_4000_chars(tmp_path: Path) -> None:
    h = Harness(db_path=tmp_path / "t.db", model="ollama/m")
    rec = h.create_session("g")
    h.store.add_turn(session_id=rec.id, step=1, role="assistant", content="", thinking="x" * 5000)
    stored = [t.thinking for t in h.store.get_turns(rec.id)]
    assert stored == ["x" * 4000]


async def test_empty_message_names_session_and_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    rec = Harness(db_path=db, model="ollama/m").create_session("g")
    assert await _async_main(["read", rec.id, "--thinking", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert f"no thinking recorded for session {rec.id}" in out
    assert "thinking-capable model" in out
