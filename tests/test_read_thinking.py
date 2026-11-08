"""#32: `tether read <id> --thinking` shows stored thinking; never replayed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.cli import _async_main
from tether.sandbox import SandboxPolicy


async def _run(tmp_path: Path) -> tuple[Path, str, FakeScriptedProvider]:
    provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd="echo hi"), thinking="SECRET plan A"),
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok")),
        ]
    )
    db = tmp_path / "t.db"
    h = Harness(
        db_path=db,
        tools=["bash"],
        provider=provider,
        max_steps=4,
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    rec = await h.run("g")
    return db, rec.id, provider


async def test_read_thinking_prints_each_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, sid, _ = await _run(tmp_path)
    capsys.readouterr()
    assert await _async_main(["read", sid, "--thinking", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "step 1: SECRET plan A" in out


async def test_read_thinking_without_any(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    rec = Harness(db_path=db, model="ollama/m").create_session("g")
    assert await _async_main(["read", rec.id, "--thinking", "--db", str(db)]) == 0
    assert "no thinking recorded" in capsys.readouterr().out


async def test_thinking_is_never_sent_to_the_model(tmp_path: Path) -> None:
    _, _, provider = await _run(tmp_path)
    assert len(provider.recorded_calls) == 2
    assert all("SECRET" not in json.dumps(m) for m in provider.recorded_calls)


def test_release_notes_mention_thinking() -> None:
    notes = Path(__file__).resolve().parents[1] / "docs" / "release-notes.md"
    unreleased = notes.read_text().split("## v", 1)[0]
    assert "thinking" in unreleased
