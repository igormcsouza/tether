"""Sandbox refusals are recorded as `sandbox_violation` turns and shown in `tether stats`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tether import api
from tether.store import SQLiteStore


def _store(tmp_path: Path) -> SQLiteStore:
    return SQLiteStore(db_path=tmp_path / "t.db")


def test_refusal_recorded_as_event(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    tid = store.add_turn(
        sid,
        1,
        "assistant",
        "refused",
        tool_cmd="bash cat .env",
        event_type="sandbox_violation",
        rule="protected path .env",
    )
    turn = next(t for t in store.get_turns(sid) if t.id == tid)
    assert turn.event_type == "sandbox_violation"
    assert turn.rule == "protected path .env"

    # A non-sandbox error keeps its own type and carries no rule.
    other = store.add_turn(sid, 2, "assistant", "x", tool_cmd="bash ls", event_type="tool_error")
    plain = next(t for t in store.get_turns(sid) if t.id == other)
    assert plain.event_type == "tool_error"
    assert plain.rule == ""


def _add_refusals(store: SQLiteStore, sid: str, counts: dict[str, int]) -> None:
    for rule, n in counts.items():
        for _ in range(n):
            store.add_turn(
                sid,
                1,
                "assistant",
                "refused",
                tool_cmd="bash cat .env",
                event_type="sandbox_violation",
                rule=rule,
            )


def test_stats_shows_top_rules(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    _add_refusals(
        store,
        sid,
        {
            "rule-a": 7,
            "rule-b": 6,
            "rule-c": 5,
            "rule-d": 4,
            "rule-e": 3,
            "rule-f": 2,
            "rule-g": 1,
        },
    )
    text = store.format_stats_report()
    assert "sandbox refusals" in text
    rows = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("rule-")]
    # Seven rules exist, only the top five are shown, most frequent first.
    assert rows == ["rule-a: 7", "rule-b: 6", "rule-c: 5", "rule-d: 4", "rule-e: 3"]


def test_stats_ties_sorted_by_rule_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    _add_refusals(store, sid, {"zeta": 1, "alpha": 1})
    text = store.format_stats_report()
    rows = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("alpha", "zeta"))]
    assert rows == ["alpha: 1", "zeta: 1"]


def test_no_block_without_refusals(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    store.add_turn(sid, 1, "assistant", "x", tool_cmd="bash ls", event_type="tool_error")
    text = store.format_stats_report()
    # The report must have models, otherwise a missing block proves nothing.
    assert "No sessions recorded." not in text
    assert "sandbox refusals" not in text


def test_stats_json_has_sandbox_refusals(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    _add_refusals(store, sid, {"rule-a": 2, "rule-b": 1})
    data = api.stats_dict(store)
    assert data["sandbox_refusals"] == [
        {"rule": "rule-a", "count": 2},
        {"rule": "rule-b", "count": 1},
    ]
    json.dumps(data)


def test_stats_json_empty_refusals_list(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    store.add_turn(sid, 1, "assistant", "x", tool_cmd="bash ls", event_type="tool_error")
    assert api.stats_dict(store)["sandbox_refusals"] == []


def test_old_db_still_opens(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    store = SQLiteStore(db_path=db)
    sid = store.create_session("fix bug").id
    store.add_turn(sid, 1, "assistant", "x", tool_cmd="bash ls", event_type="tool_error")
    store.close()
    # Simulate a database created before the `rule` column existed.
    conn = sqlite3.connect(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(turns)")}
    assert "rule" in cols  # the column must exist before the test can drop it
    conn.execute("ALTER TABLE turns DROP COLUMN rule")
    conn.commit()
    conn.close()

    reopened = SQLiteStore(db_path=db)  # must migrate, not fail
    assert reopened.get_stats().sandbox_refusals == []
    assert "sandbox refusals" not in reopened.format_stats_report()
    events = api.events(reopened, sid)
    assert events[0]["event"] == "tool_error"


def test_retro_still_sees_violations(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    store.add_turn(
        sid,
        1,
        "assistant",
        "x",
        tool_cmd="bash cat .env",
        event_type="sandbox_violation",
        rule="protected path .env",
    )
    store.add_turn(sid, 1, "tool", "Sandbox violation: protected path .env. Instead: x.")
    trace = store.extract_friction_trace(sid)
    assert any("failed[sandbox_violation]" in line for line in trace)
    # Friction offenders count the refusal like a tool_error.
    report = store.get_stats()
    offender = next(o for o in report.offenders if o.command == "bash")
    assert offender.tool_errors == 1
    assert offender.total_friction == 1


def test_events_lists_new_type(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session("fix bug").id
    _add_refusals(store, sid, {"rule-a": 1})
    assert [ev["event"] for ev in api.events(store, sid)] == ["sandbox_violation"]
