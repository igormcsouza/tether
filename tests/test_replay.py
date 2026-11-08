"""Tests for `tether replay` (CLI and Harness.from_session)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, ModelResponse, SQLiteStore
from tether import harness as harness_mod
from tether.cli import _async_main

DONE = ModelResponse(content="", action=ActionCall(cmd="done", stdin='{"ok": true}'))


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[SQLiteStore, str, Any]:
    db = str(tmp_path / "t.db")
    monkeypatch.setattr(
        harness_mod, "resolve_provider", lambda model, **kw: FakeScriptedProvider([DONE])
    )
    store = SQLiteStore(db_path=db)
    orig = store.create_session(
        goal="g", model="fake/a", tools=["bash"], sandbox_config={}, max_steps=5
    )
    return store, db, orig


async def test_replay_unknown_id_exits_1(
    setup: tuple[SQLiteStore, str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    _, db, _ = setup
    assert await _async_main(["replay", "ses_nope", "--db", db]) == 1
    assert "not found" in capsys.readouterr().err


async def test_replay_refuses_running_session(
    setup: tuple[SQLiteStore, str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    store, db, orig = setup
    store.update_session(orig.id, status="RUNNING", pid=os.getpid())
    assert await _async_main(["replay", orig.id, "--db", db]) == 1
    assert "still RUNNING" in capsys.readouterr().err
    assert store.list_sessions(parent_id=orig.id) == []


async def test_replay_sets_parent_and_overrides_model(
    setup: tuple[SQLiteStore, str, Any],
) -> None:
    store, db, orig = setup
    argv = ["replay", orig.id, "--model", "fake/b", "--max-steps", "3", "--db", db]
    assert await _async_main(argv) == 0
    child = store.list_sessions(parent_id=orig.id)[0]
    assert child.parent_id == orig.id
    assert child.model == "fake/b"
    assert child.max_steps == 3
    assert child.goal == "g"
    assert child.tools == ["bash"]


async def test_replay_defaults_to_original_model(
    setup: tuple[SQLiteStore, str, Any],
) -> None:
    store, db, orig = setup
    assert await _async_main(["replay", orig.id, "--db", db]) == 0
    child = store.list_sessions(parent_id=orig.id)[0]
    assert child.model == "fake/a"
    assert child.max_steps == 5


async def test_replay_text_table(
    setup: tuple[SQLiteStore, str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    _, db, orig = setup
    assert await _async_main(["replay", orig.id, "--db", db]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("replay of ses_")
    assert "original" in lines[1] and "replay" in lines[1]
    assert [line.split()[0] for line in lines[3:7]] == ["status", "steps", "tokens", "wall_s"]
    assert lines[3].endswith("COMPLETED")


async def test_replay_json_shape(
    setup: tuple[SQLiteStore, str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    store, db, orig = setup
    assert await _async_main(["replay", orig.id, "--json", "--db", db]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"original", "replay"}
    child = store.list_sessions(parent_id=orig.id)[0]
    assert set(data["replay"]) == {"id", "model", "status", "steps", "tokens", "wall_s"}
    assert data["replay"]["id"] == child.id
    assert data["replay"]["tokens"] == child.total_prompt_tokens + child.total_completion_tokens


async def test_replay_restores_output_schema_and_params(
    setup: tuple[SQLiteStore, str, Any],
) -> None:
    store, db, _ = setup
    schema = {"type": "object"}
    orig = store.create_session(
        goal="g",
        model="fake/a",
        tools=["bash"],
        sandbox_config={"output_schema": schema, "params": {"temperature": 0}},
        max_steps=5,
    )
    assert await _async_main(["replay", orig.id, "--db", db]) == 0
    child = store.list_sessions(parent_id=orig.id)[0]
    assert child.sandbox_config["output_schema"] == schema
    assert child.sandbox_config["params"] == {"temperature": 0}


async def test_replay_run_error_exits_1(
    setup: tuple[SQLiteStore, str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, db, orig = setup

    async def boom(self: Any, goal: str, *, parent_id: str | None = None) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(harness_mod.Harness, "run", boom)
    assert await _async_main(["replay", orig.id, "--db", db]) == 1
    captured = capsys.readouterr()
    assert "replay failed" in captured.err and "boom" in captured.err
    assert captured.out == ""


async def test_replay_rejects_zero_max_steps(
    setup: tuple[SQLiteStore, str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    _, db, orig = setup
    with pytest.raises(SystemExit) as exc:
        await _async_main(["replay", orig.id, "--max-steps", "0", "--db", db])
    assert exc.value.code == 2
    assert "max-steps" in capsys.readouterr().err
