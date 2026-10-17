"""Unit tests for tether/store.py (SQLite WAL state, thread-local connections, FTS5 BM25 RAG)."""

from __future__ import annotations

import time
from pathlib import Path

from tether.store import GLOBAL_SESSION_ID, SQLiteStore, _sanitize_fts_tokens, chunk_text


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
