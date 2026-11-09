"""Column layout of `tether replay` and `tether list`, and `replay --worktree` (#279)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, ModelResponse, SQLiteStore
from tether import harness as harness_mod
from tether.cli import _async_main, _format_compare
from tether.worktree import WorktreeError

DONE = ModelResponse(content="", action=ActionCall(cmd="done", stdin='{"ok": true}'))
MODEL = "ollama/qwen3.5:9b"
LONG_MODEL = "ollama/" + "q" * 23  # 30 characters


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    monkeypatch.setattr(
        harness_mod, "resolve_provider", lambda model, **kw: FakeScriptedProvider([DONE])
    )
    db = str(tmp_path / "t.db")
    orig = SQLiteStore(db_path=db).create_session(
        goal="g", model="fake/a", tools=["bash"], sandbox_config={}, max_steps=5
    )
    return db, orig.id


def _summary(sid: str, model: str) -> dict[str, object]:
    return {
        "id": sid,
        "model": model,
        "status": "COMPLETED",
        "steps": 1,
        "tokens": 10,
        "wall_s": 0.5,
    }


def test_replay_columns_fit_long_model_ids() -> None:
    text = _format_compare(_summary("ses_orig", LONG_MODEL), _summary("ses_rep", LONG_MODEL))
    model_row = next(line for line in text.splitlines() if line.startswith("model"))
    assert f"{LONG_MODEL}  {LONG_MODEL}" in model_row


async def test_list_aligns_waiting_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db_path=db)
    done = store.create_session(
        goal="done goal", model=MODEL, tools=["bash"], sandbox_config={}, max_steps=5
    )
    waiting = store.create_session(
        goal="wait goal", model=MODEL, tools=["bash"], sandbox_config={}, max_steps=5
    )
    store.update_session(done.id, status="COMPLETED")
    store.update_session(waiting.id, status="WAITING_INPUT")
    assert await _async_main(["list", "--db", db]) == 0
    header, *rows = capsys.readouterr().out.splitlines()
    assert len(rows) == 2
    model_offset = header.index("MODEL")
    for row in rows:
        assert row.index(MODEL) == model_offset, row


async def test_replay_worktree_flags_are_passed_through(
    seeded: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    db, orig_id = seeded
    captured: dict[str, Any] = {}

    def fake_from_session(cls: type[Any], rec: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return harness_mod.Harness(db_path=db, model="fake/a")

    monkeypatch.setattr(harness_mod.Harness, "from_session", classmethod(fake_from_session))
    argv = [
        'replay', orig_id, '--worktree', '--worktree-from', 'main',
        '--setup', 'make test', '--db', db,
    ]  # fmt: skip
    assert await _async_main(argv) == 0
    assert captured["worktree"] is True
    assert captured["worktree_from"] == "main"
    assert captured["setup"] == "make test"


async def test_replay_setup_without_worktree_is_usage_error(
    seeded: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    db, orig_id = seeded
    assert await _async_main(["replay", orig_id, "--setup", "make", "--db", db]) == 2
    assert "need --worktree" in capsys.readouterr().err


async def test_replay_worktree_outside_git_repo_exits_1(
    seeded: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db, orig_id = seeded
    monkeypatch.chdir(tmp_path)
    assert await _async_main(["replay", orig_id, "--worktree", "--db", db]) == 1
    err = capsys.readouterr().err
    assert "needs a git repository" in err
    assert "Traceback" not in err


async def test_replay_setup_failure_still_prints_comparison(
    seeded: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db, orig_id = seeded
    monkeypatch.setattr(harness_mod, "repo_root", lambda cwd: tmp_path)
    monkeypatch.setattr(
        harness_mod,
        "create_worktree",
        lambda root, sid, base: (tmp_path / sid, f"tether/{sid}"),
    )
    monkeypatch.setattr(harness_mod, "run_setup", lambda path, cmd: "setup exploded")
    argv = ["replay", orig_id, "--worktree", "--setup", "false", "--db", db]
    assert await _async_main(argv) == 0
    assert capsys.readouterr().out.splitlines()[0].startswith(f"replay of {orig_id}")
    child = SQLiteStore(db_path=db).list_sessions(parent_id=orig_id)[0]
    assert child.sandbox_config["setup_failed"] is True


async def test_replay_plain_does_not_create_worktree(
    seeded: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, orig_id = seeded
    calls: list[str] = []

    def fake_create(root: Path, sid: str, base: str | None) -> tuple[Path, str]:
        calls.append(sid)
        return tmp_path / sid, f"tether/{sid}"

    monkeypatch.setattr(harness_mod, "repo_root", lambda cwd: tmp_path)
    monkeypatch.setattr(harness_mod, "create_worktree", fake_create)
    assert await _async_main(["replay", orig_id, "--db", db]) == 0
    assert calls == []
    assert await _async_main(["replay", orig_id, "--worktree", "--db", db]) == 0
    assert len(calls) == 1


async def test_replay_worktree_error_prints_its_own_message(
    seeded: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db, orig_id = seeded
    monkeypatch.setattr(harness_mod, "repo_root", lambda cwd: tmp_path)

    def boom(root: Path, sid: str, base: str | None) -> tuple[Path, str]:
        raise WorktreeError("git worktree add failed: boom")

    monkeypatch.setattr(harness_mod, "create_worktree", boom)
    assert await _async_main(["replay", orig_id, "--worktree", "--db", db]) == 1
    err = capsys.readouterr().err
    assert "git worktree add failed: boom" in err
    assert "Check --model" not in err
