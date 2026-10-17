"""Tests for friction extraction and `tether retro`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether.providers.base import ModelResponse
from tether.retro import SECTION, parse_rules, run_retro
from tether.store import SQLiteStore


def _friction_session(store: SQLiteStore, skill: str | None = None) -> str:
    s = store.create_session("fix bug", skill=skill)
    t1 = store.add_turn(s.id, 1, "assistant", "x", tool_cmd="edit wrte f.py")
    store.update_turn_telemetry(t1, event_type="syntax_error")
    store.add_turn(s.id, 1, "tool", "Error: unknown subcommand `wrte`")
    store.add_turn(s.id, 2, "assistant", "x", tool_cmd="edit write f.py")
    t3 = store.add_turn(s.id, 3, "assistant", "x", tool_cmd="bash ls")
    store.update_turn_telemetry(t3, event_type="loop_stall")
    store.add_turn(s.id, 3, "tool", "[LOOP DETECTED] You just ran `bash ls`")
    store.add_turn(s.id, 4, "user", "[Follow-up instruction]: use pytest -q")
    store.add_turn(s.id, 5, "assistant", "x", tool_cmd="done")
    return s.id


def test_friction_trace(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "t.db")
    sid = _friction_session(store)
    trace = store.extract_friction_trace(sid)
    assert len(trace) == 3
    assert "unknown subcommand" in trace[0] and "then: `edit write f.py`" in trace[0]
    assert "LOOP DETECTED" in trace[1]
    assert trace[2] == "correction: use pytest -q"
    assert store.extract_friction_trace(store.create_session("clean").id) == []


def test_parse_rules_caps_and_dedups() -> None:
    long = "- " + "word " * 80
    out = parse_rules(
        f"- Use pytest -q\n- use  PYTEST q!\n{long}\n- Run edit --help first\n- c",
        "- Run edit --help first",
    )
    assert out == ["Use pytest -q", "c"]


@pytest.mark.asyncio
async def test_retro_diff_and_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = tmp_path / "skills" / "fixer.md"
    skill.parent.mkdir()
    skill.write_text("---\nname: fixer\n---\nFix bugs.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    store = SQLiteStore(db_path=tmp_path / "t.db")
    sid = _friction_session(store, skill="fixer")
    resp = ModelResponse(content="- Run `edit --help` before writing.")

    diff = await run_retro(store, sid, provider=FakeScriptedProvider([resp]))
    assert "+- Run `edit --help`" in diff and SECTION not in skill.read_text()

    await run_retro(store, sid, apply=True, provider=FakeScriptedProvider([resp]))
    assert SECTION in skill.read_text()
    again = await run_retro(store, sid, apply=True, provider=FakeScriptedProvider([resp]))
    assert "No new rules" in again and skill.read_text().count("edit --help") == 1


async def test_retro_edge_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    store = SQLiteStore(db_path=tmp_path / "t.db")
    with pytest.raises(ValueError):
        await run_retro(store, "ses_nope")
    assert "No friction" in await run_retro(store, store.create_session("clean").id)

    sid = _friction_session(store)  # no skill -> project pins
    junk = FakeScriptedProvider([ModelResponse(content="no bullets")])
    assert "No new rules" in await run_retro(store, sid, provider=junk)
    good = ModelResponse(content="- Run `edit --help` first.")
    out = await run_retro(store, sid, provider=FakeScriptedProvider([good]))
    assert "pinned" not in out and not store.get_pins("__project__")
    out = await run_retro(store, sid, apply=True, provider=FakeScriptedProvider([good]))
    assert "pinned" in out and len(store.get_pins("__project__")) == 1


async def test_cli_retro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tether.cli import _async_main

    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "t.db")
    assert await _async_main(["retro", "ses_nope", "--db", db]) == 1
    store = SQLiteStore(db_path=db)
    assert await _async_main(["retro", store.create_session("g").id, "--db", db]) == 0


def test_append_rules_existing_section() -> None:
    from tether.retro import append_rules

    assert append_rules(f"x\n\n{SECTION}\n- a\n", ["b"]).endswith("- a\n- b\n")
