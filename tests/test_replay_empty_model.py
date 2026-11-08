"""Review fix: `tether replay --model ""` is a usage error, not a silent replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import Harness
from tether.cli import _async_main


async def test_empty_model_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    rec = Harness(db_path=db, model="ollama/m").create_session("g")
    assert await _async_main(["replay", rec.id, "--model", "", "--db", str(db)]) == 1
    assert "model" in capsys.readouterr().err
    assert Harness(db_path=db).store.list_sessions(limit=10)[0].id == rec.id  # nothing new


def test_readme_lists_replay() -> None:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    assert "tether replay" in readme.read_text()
