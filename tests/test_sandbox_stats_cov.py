"""Harness-level and edge-case coverage for sandbox_violation events (S6 QA/review)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, tool
from tether.sandbox import _refusal
from tether.store import SQLiteStore, sandbox_rule
from tether.tools.web import PrivateAddressError


def _script(cmd: str) -> list[ModelResponse]:
    return [
        ModelResponse(content="", action=ActionCall(cmd=cmd), prompt_tokens=5, completion_tokens=2),
        ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"), prompt_tokens=5),
    ]


async def _drive(tmp_path: Path, tool_fn: object, name: str, cmd: str) -> list[tuple[str, str]]:
    db = tmp_path / "tether.db"
    harness = Harness(
        db_path=db,
        tools=[tool_fn],
        provider=FakeScriptedProvider(_script(cmd)),
        max_steps=5,
    )
    rec = harness.create_session("goal")
    await harness.execute_session(rec.id)
    return [
        (t.event_type, t.rule)
        for t in harness.store.get_turns(rec.id)
        if t.role == "assistant" and t.event_type != "ok"
    ]


async def test_harness_refused_command_recorded_with_rule(tmp_path: Path) -> None:
    @tool(name="guarded", description="A tool the sandbox refuses")
    def guarded(path: str) -> str:
        raise _refusal("protected path .env", "use a copy outside .env")

    events = await _drive(tmp_path, guarded, "guarded", "guarded .env")
    assert ("sandbox_violation", "protected path .env") in events


async def test_harness_private_address_stays_tool_error(tmp_path: Path) -> None:
    @tool(name="fetch", description="Fetch a URL")
    def fetch(url: str) -> str:
        raise PrivateAddressError("loopback address refused")

    events = await _drive(tmp_path, fetch, "fetch", "fetch http://127.0.0.1")
    assert ("tool_error", "") in events
    assert not any(ev == "sandbox_violation" for ev, _ in events)


def test_unparseable_message_is_unknown_rule() -> None:
    assert sandbox_rule("Sandbox violation: no instead clause here") == "(unknown)"
    assert sandbox_rule("totally different text") == "(unknown)"


def test_long_rule_truncated_to_80_chars() -> None:
    long_rule = "x" * 120
    assert sandbox_rule(f"Sandbox violation: {long_rule}. Instead: y.") == "x" * 80


def test_pipeline_root_rows_excluded_from_refusals(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "t.db")
    root = store.create_session("pipe", sandbox_config={"pipeline": True}).id
    store.add_turn(
        root,
        1,
        "assistant",
        "refused",
        tool_cmd="bash cat .env",
        event_type="sandbox_violation",
        rule="protected path .env",
    )
    report = store.get_stats()
    assert report.sandbox_refusals == []
    assert report.models == []


def test_migrated_old_row_reads_empty_rule(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    store = SQLiteStore(db_path=db)
    sid = store.create_session("fix bug").id
    tid = store.add_turn(sid, 1, "assistant", "x", tool_cmd="bash ls", event_type="tool_error")
    store.close()
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE turns DROP COLUMN rule")
    conn.commit()
    conn.close()

    reopened = SQLiteStore(db_path=db)
    turn = next(t for t in reopened.get_turns(sid) if t.id == tid)
    assert turn.rule == ""


async def test_tether_events_cli_shows_sandbox_violation(tmp_path: Path, capsys: object) -> None:
    import pytest

    from tether.cli import _async_main

    assert isinstance(capsys, pytest.CaptureFixture)
    db = tmp_path / "cli.db"
    store = SQLiteStore(db_path=db)
    sid = store.create_session("fix bug").id
    store.add_turn(
        sid,
        1,
        "assistant",
        "refused",
        tool_cmd="bash cat .env",
        event_type="sandbox_violation",
        rule="protected path .env",
    )
    store.close()
    capsys.readouterr()
    assert await _async_main(["events", sid, "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert '"event": "sandbox_violation"' in out
