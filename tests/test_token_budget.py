# Token budget cap: max_tokens pauses a session as WAITING_INPUT, and send extends it by the grant.

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import api
from tether.cli import _async_main
from tether.harness import Harness
from tether.mcp import TetherMCP, ToolError
from tether.providers.base import ActionCall, ModelResponse
from tether.store import SessionRecord, SQLiteStore


def _act(cmd: str, stdin: str | None = None, prompt: int = 6, completion: int = 6) -> ModelResponse:
    return ModelResponse(
        content="",
        action=ActionCall(cmd=cmd, stdin=stdin),
        prompt_tokens=prompt,
        completion_tokens=completion,
    )


async def _paused(db: Path) -> SessionRecord:
    harness = Harness(max_tokens=10, db_path=db, provider=FakeScriptedProvider([_act("ls")]))
    return await harness.run("g")


async def test_budget_pauses_waiting_input(tmp_path: Path) -> None:
    rec = await _paused(tmp_path / "db.sqlite")
    assert rec.status == "WAITING_INPUT"
    assert rec.step_count == 1
    assert rec.result is not None
    assert rec.result.startswith("[TOKEN BUDGET] used 12 of 10 tokens after 1 steps")


async def test_budget_exit_code_is_2(tmp_path: Path) -> None:
    rec = await _paused(tmp_path / "db.sqlite")
    assert api.exit_code(rec) == 2


async def test_no_cap_by_default(tmp_path: Path) -> None:
    provider = FakeScriptedProvider([_act("ls"), _act("ls"), _act("ls"), _act("done", stdin="ok")])
    rec = await Harness(db_path=tmp_path / "db.sqlite", provider=provider).run("g")
    assert rec.status == "COMPLETED"
    assert rec.max_tokens is None
    assert "max_tokens" not in api.session_dict(rec)


async def test_send_extends_budget_by_grant(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    rec = await _paused(db)
    provider = FakeScriptedProvider([_act("done", stdin="ok", prompt=1, completion=2)])
    resumed = await Harness(max_tokens=10, db_path=db, provider=provider).send(rec.id, "more")
    stored = SQLiteStore(db_path=db).get_session(rec.id)
    assert stored is not None
    assert stored.max_tokens == 22
    assert resumed.status == "COMPLETED"


def test_zero_budget_is_harness_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        Harness(max_tokens=0, db_path=tmp_path / "db.sqlite")


async def test_zero_budget_cli_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = await _async_main(["run", "--max-tokens", "0", "g"])
    assert code == api.EXIT_USAGE
    assert "--max-tokens must be a positive integer" in capsys.readouterr().err


async def test_mcp_tether_run_max_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Harness, "spawn", lambda self, goal, **_: self.create_session(goal).id)
    db = tmp_path / "db.sqlite"
    mcp = TetherMCP(db, tmp_path)
    out = await mcp.call("tether_run", {"goal": "g", "wait": False, "max_tokens": 5})
    rec = SQLiteStore(db_path=db).get_session(out["id"])
    assert rec is not None
    assert rec.max_tokens == 5
    assert rec.token_grant == 5
    with pytest.raises(ToolError, match="positive integer"):
        await mcp.call("tether_run", {"goal": "g", "wait": False, "max_tokens": 0})


async def test_store_migrates_old_db(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, parent_id TEXT, status TEXT NOT NULL, "
            "model TEXT NOT NULL, skill TEXT, tools_json TEXT NOT NULL, "
            "sandbox_json TEXT NOT NULL, "
            "goal TEXT NOT NULL, result TEXT, step_count INTEGER NOT NULL DEFAULT 0, "
            "max_steps INTEGER NOT NULL DEFAULT 15, peak_tokens INTEGER NOT NULL DEFAULT 0, "
            "total_prompt_tokens INTEGER NOT NULL DEFAULT 0, "
            "total_completion_tokens INTEGER NOT NULL DEFAULT 0, pid INTEGER, "
            "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO sessions (id, status, model, tools_json, sandbox_json, goal, "
            "created_at, updated_at) "
            "VALUES ('ses_old', 'COMPLETED', 'm', '[]', '{}', 'g', 1, 1)"
        )
    rec = SQLiteStore(db_path=db).get_session("ses_old")
    assert rec is not None
    assert rec.max_tokens is None
    assert rec.token_grant is None
    with sqlite3.connect(db) as conn:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(sessions)")}
    assert {"max_tokens", "token_grant"} <= cols


async def test_session_dict_reports_max_tokens(tmp_path: Path) -> None:
    rec = await _paused(tmp_path / "db.sqlite")
    assert api.session_dict(rec)["max_tokens"] == 10
