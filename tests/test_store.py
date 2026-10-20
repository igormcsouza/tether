"""Unit tests for tether/store.py (SQLite WAL state, thread-local connections, FTS5 BM25 RAG)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from tether.store import (
    GLOBAL_SESSION_ID,
    SQLiteStore,
    _sanitize_fts_tokens,
    canonical_tool_command,
    chunk_text,
)


def test_sqlite_connection_reuse_and_crud(tmp_path: Path) -> None:
    """Verify thread-local SQLite connection caching, session CRUD, and FTS5 chunking."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    conn1 = store._connect()
    conn2 = store._connect()
    assert conn1 is conn2
    store.close()
    conn3 = store._connect()
    assert conn3 is not conn1
    store.close()

    assert chunk_text("") == []
    long_para = ("word " * 150) + "\n" + ("X" * 700) + "\n" + ("short line\n" * 40)
    chunks = chunk_text(f"# Heading 1\n\n{long_para}\n\n# Heading 2\n\nSmall block", max_chars=200)
    assert len(chunks) >= 4
    assert _sanitize_fts_tokens("the and or") == ["the", "and", "or"]

    text_with_empty_block = "# H1\n\n\n# H2\n\n" + ("A" * 50) + "\n\n" + ("B" * 50)
    chunks1 = chunk_text(text_with_empty_block, max_chars=70)
    assert len(chunks1) >= 2

    oversized_block = "short_first_line\n" + ("L" * 150)
    chunks2 = chunk_text(oversized_block, max_chars=50)
    assert any("short_first_line" in c for c in chunks2)

    s1 = store.create_session("Goal 1")
    store.update_session(s1.id, pid=999, tools=["web", "mem"])
    assert store.list_sessions(limit=5)[0].pid == 999
    store.index_text(s1.id, "observation", "obs_1", "Alpha beta gamma delta")
    assert store.search_chunks("   ", session_ids=[s1.id]) == []
    assert store.search_chunks("anything", session_ids=[]) == []

    hits = store.search_chunks(
        "Alpha nonexistent_token",
        session_ids=[s1.id],
        source_types=["observation"],
    )
    assert len(hits) == 1
    assert "not found" in store.get_session_digest("ses_nope")
    store.update_session(s1.id, result="R" * 200)
    assert "..." in store.get_session_digest(s1.id)
    store.close()


def test_project_memory_and_episodic_rag(tmp_path: Path) -> None:
    """Verify GLOBAL_SESSION_ID pins and sub-millisecond cross-session BM25 RAG."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    assert GLOBAL_SESSION_ID == "__project__"

    store.set_pin(GLOBAL_SESSION_ID, "db_engine", "SQLite WAL with FTS5 Porter tokenizer")
    assert store.get_pins(GLOBAL_SESSION_ID) == {
        "db_engine": "SQLite WAL with FTS5 Porter tokenizer"
    }

    s_done = store.create_session("Completed session")
    store.update_session(
        s_done.id,
        status="COMPLETED",
        result="Implemented zero-bloat sub-agent orchestration using bwrap sandbox.",
    )

    s_failed = store.create_session("Failed session")
    store.update_session(
        s_failed.id,
        status="FAILED",
        result="Unverified hallucinated approach with broken imports.",
    )

    project_ids = store.get_project_session_ids()
    assert GLOBAL_SESSION_ID in project_ids
    assert s_done.id in project_ids
    assert s_failed.id not in project_ids

    t0 = time.perf_counter()
    hits_pin = store.search_project_chunks("Porter tokenizer")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 50.0
    assert len(hits_pin) == 1
    assert hits_pin[0].session_id == GLOBAL_SESSION_ID
    assert hits_pin[0].source_type == "pin"

    hits_done = store.search_project_chunks("bwrap sandbox")
    assert len(hits_done) == 1
    assert hits_done[0].session_id == s_done.id
    assert hits_done[0].source_type == "result"

    assert store.search_project_chunks("hallucinated") == []
    assert store.remove_pin(GLOBAL_SESSION_ID, "db_engine") is True
    assert store.search_project_chunks("Porter tokenizer") == []
    store.close()


def test_telemetry_migration_and_stats_aggregation(tmp_path: Path) -> None:
    """Verify legacy DB migration, canonical_tool_command, and get_stats / format_stats_report."""
    assert canonical_tool_command(None) == "unknown"
    assert canonical_tool_command("   ") == "unknown"
    assert canonical_tool_command('""') == "unknown"
    assert canonical_tool_command("$ tether edit replace a.py --lines 1:2") == "edit replace"
    assert canonical_tool_command("`bash pytest -q`") == "bash"

    legacy_db = tmp_path / "legacy.db"
    with sqlite3.connect(str(legacy_db)) as raw_conn:
        raw_conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                status TEXT NOT NULL,
                model TEXT NOT NULL,
                skill TEXT,
                tools_json TEXT NOT NULL,
                sandbox_json TEXT NOT NULL,
                goal TEXT NOT NULL,
                result TEXT,
                step_count INTEGER NOT NULL DEFAULT 0,
                max_steps INTEGER NOT NULL DEFAULT 15,
                peak_tokens INTEGER NOT NULL DEFAULT 0,
                pid INTEGER,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_cmd TEXT,
                tool_stdin TEXT,
                obs_id TEXT,
                created_at REAL NOT NULL
            );
            """
        )

    store = SQLiteStore(db_path=legacy_db)
    assert store.format_stats_report() == "No sessions recorded."

    s1 = store.create_session("Goal 1", model="ollama/qwen3.5:9b", skill="coder")
    store.update_session(
        s1.id,
        status="COMPLETED",
        step_count=3,
        peak_tokens=500,
        add_prompt_tokens=400,
        add_completion_tokens=100,
    )
    t1 = store.add_turn(
        s1.id,
        step=1,
        role="assistant",
        content="thinking",
        prompt_tokens=120,
        completion_tokens=30,
        duration_ms=45,
        event_type="nudge",
    )
    store.update_turn_telemetry(t1)  # no-op when no fields specified
    t2 = store.add_turn(
        s1.id,
        step=2,
        role="assistant",
        content="",
        tool_cmd="edit replace foo.py",
        prompt_tokens=140,
        completion_tokens=35,
        duration_ms=50,
    )
    store.update_turn_telemetry(t2, event_type="syntax_error", duration_ms=55)
    t3 = store.add_turn(
        s1.id,
        step=3,
        role="assistant",
        content="",
        tool_cmd="bash pytest",
        event_type="loop_stall",
    )
    assert t3 > 0
    store.add_turn(
        s1.id, step=3, role="assistant", content="", tool_cmd="bash ls", event_type="cycle_stall"
    )
    store.add_turn(
        s1.id,
        step=3,
        role="assistant",
        content="",
        tool_cmd="edit view missing.py",
        event_type="tool_error",
    )

    s2 = store.create_session("Goal 2", model="openai/gpt-4o-mini", skill="researcher")
    store.update_session(
        s2.id,
        status="FAILED",
        step_count=2,
        peak_tokens=300,
        add_prompt_tokens=250,
        add_completion_tokens=50,
    )

    report = store.get_stats(model="ollama/qwen3.5:9b", skill="coder", limit=10)
    assert len(report.models) == 1
    m = report.models[0]
    assert m.runs == 1
    assert m.pass_rate == 100.0
    assert m.total_tokens == 500
    assert m.nudges == 1
    assert m.syntax_errors == 1
    assert m.loop_stalls == 1
    assert m.cycle_stalls == 1
    assert m.tool_errors == 1
    assert len(report.offenders) == 3
    assert {o.command: o.cycle_stalls for o in report.offenders}["bash"] == 1

    formatted = store.format_stats_report()
    assert "MODEL" in formatted
    assert "CYCLES" in formatted
    assert "ollama/qwen3.5:9b" in formatted
    assert "openai/gpt-4o-mini" in formatted
    assert "Top Friction Offenders (by command):" in formatted
    assert "edit replace" in formatted
    store.close()
