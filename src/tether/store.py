"""SQLite WAL state persistence and FTS5 BM25 RAG chunk store for Tether."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SessionRecord:
    id: str
    parent_id: str | None
    status: str  # PENDING | RUNNING | COMPLETED | FAILED
    model: str
    skill: str | None
    tools: list[str]
    sandbox_config: dict[str, Any]
    goal: str
    result: str | None
    step_count: int
    max_steps: int
    peak_tokens: int
    pid: int | None
    created_at: float
    updated_at: float


@dataclass(slots=True)
class TurnRecord:
    id: int
    session_id: str
    step: int
    role: str
    content: str
    tool_cmd: str | None
    tool_stdin: str | None
    obs_id: str | None
    created_at: float


@dataclass(slots=True)
class ObservationRecord:
    id: str
    session_id: str
    step: int
    cmd: str
    raw_output: str
    summary: str
    char_len: int


@dataclass(slots=True)
class ChunkHit:
    session_id: str
    source_type: str  # result | observation | pin
    source_id: str
    chunk_index: int
    content: str
    score: float


def chunk_text(text: str, max_chars: int = 600) -> list[str]:
    """Split markdown or plain text into ~150-token chunks along headings and paragraphs."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    # Split by markdown headings or blank lines first
    blocks = re.split(r"\n(?=#{1,4}\s)|\n\s*\n", cleaned)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for raw_block in blocks:
        block = raw_block.strip()
        if len(block) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            # Split oversized block by lines or fixed window
            lines = block.splitlines()
            buf: list[str] = []
            buf_len = 0
            for line in lines:
                if len(line) > max_chars:
                    if buf:
                        chunks.append("\n".join(buf))
                        buf = []
                        buf_len = 0
                    for i in range(0, len(line), max_chars):
                        chunks.append(line[i : i + max_chars])
                elif buf_len + len(line) + 1 > max_chars and buf:
                    chunks.append("\n".join(buf))
                    buf = [line]
                    buf_len = len(line)
                else:
                    buf.append(line)
                    buf_len += len(line) + 1
            if buf:
                chunks.append("\n".join(buf))
        elif current_len + len(block) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += len(block) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _sanitize_fts_tokens(query: str) -> list[str]:
    """Extract safe alphanumeric search tokens for SQLite FTS5."""
    tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
    stopwords = {"the", "a", "an", "of", "to", "in", "for", "on", "with", "is", "are", "and", "or"}
    filtered = [t for t in tokens if len(t) > 1 and t not in stopwords]
    return filtered or tokens


class SQLiteStore:
    """ACID SQLite WAL state and FTS5 BM25 RAG store."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        resolved = db_path or os.environ.get("TETHER_DB") or ".tether/tether.db"
        self.db_path = Path(resolved).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA mmap_size=134217728;")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Close the current thread's cached SQLite connection."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
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

                CREATE TABLE IF NOT EXISTS turns (
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
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, step);

                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    cmd TEXT NOT NULL,
                    raw_output TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    char_len INTEGER NOT NULL,
                    PRIMARY KEY (session_id, id)
                );

                CREATE TABLE IF NOT EXISTS pins (
                    session_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (session_id, key)
                );

                CREATE TABLE IF NOT EXISTS inbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_inbox_session ON inbox(session_id, consumed);

                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    session_id UNINDEXED,
                    source_type UNINDEXED,
                    source_id UNINDEXED,
                    chunk_index UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                );
                """
            )

    def create_session(
        self,
        goal: str,
        model: str = "ollama/qwen3.5:9b",
        skill: str | None = None,
        tools: list[str] | None = None,
        sandbox_config: dict[str, Any] | None = None,
        parent_id: str | None = None,
        max_steps: int = 15,
        session_id: str | None = None,
    ) -> SessionRecord:
        sid = session_id or f"ses_{uuid.uuid4().hex[:8]}"
        now = time.time()
        tools_list = list(tools) if tools else []
        sbox = sandbox_config or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, parent_id, status, model, skill, tools_json, sandbox_json,
                    goal, result, step_count, max_steps, peak_tokens, pid, created_at, updated_at
                ) VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?, NULL, 0, ?, 0, NULL, ?, ?)
                """,
                (
                    sid,
                    parent_id,
                    model,
                    skill,
                    json.dumps(tools_list),
                    json.dumps(sbox),
                    goal,
                    max_steps,
                    now,
                    now,
                ),
            )
        rec = self.get_session(sid)
        assert rec is not None
        return rec

    def _row_to_session(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=str(row["id"]),
            parent_id=row["parent_id"],
            status=str(row["status"]),
            model=str(row["model"]),
            skill=row["skill"],
            tools=json.loads(str(row["tools_json"])),
            sandbox_config=json.loads(str(row["sandbox_json"])),
            goal=str(row["goal"]),
            result=row["result"],
            step_count=int(row["step_count"]),
            max_steps=int(row["max_steps"]),
            peak_tokens=int(row["peak_tokens"]),
            pid=int(row["pid"]) if row["pid"] is not None else None,
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return self._row_to_session(row) if row else None

    def list_sessions(self, parent_id: str | None = None, limit: int = 50) -> list[SessionRecord]:
        with self._connect() as conn:
            if parent_id is not None:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE parent_id = ? ORDER BY created_at DESC LIMIT ?",
                    (parent_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [self._row_to_session(r) for r in rows]

    def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        model: str | None = None,
        result: str | None = None,
        step_count: int | None = None,
        peak_tokens: int | None = None,
        pid: int | None = None,
        tools: list[str] | None = None,
    ) -> None:
        updates: list[str] = ["updated_at = ?"]
        params: list[Any] = [time.time()]
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if model is not None:
            updates.append("model = ?")
            params.append(model)
        if result is not None:
            updates.append("result = ?")
            params.append(result)
        if step_count is not None:
            updates.append("step_count = ?")
            params.append(step_count)
        if peak_tokens is not None:
            updates.append("peak_tokens = MAX(peak_tokens, ?)")
            params.append(peak_tokens)
        if pid is not None:
            updates.append("pid = ?")
            params.append(pid)
        if tools is not None:
            updates.append("tools_json = ?")
            params.append(json.dumps(tools))

        params.append(session_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
        if result is not None:
            self.index_text(session_id, "result", "final", result)

    def add_turn(
        self,
        session_id: str,
        step: int,
        role: str,
        content: str,
        tool_cmd: str | None = None,
        tool_stdin: str | None = None,
        obs_id: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO turns (
                    session_id, step, role, content, tool_cmd, tool_stdin, obs_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, step, role, content, tool_cmd, tool_stdin, obs_id, time.time()),
            )
            return int(cur.lastrowid or 0)

    def get_turns(self, session_id: str) -> list[TurnRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY id ASC", (session_id,)
            ).fetchall()
            return [
                TurnRecord(
                    id=int(r["id"]),
                    session_id=str(r["session_id"]),
                    step=int(r["step"]),
                    role=str(r["role"]),
                    content=str(r["content"]),
                    tool_cmd=r["tool_cmd"],
                    tool_stdin=r["tool_stdin"],
                    obs_id=r["obs_id"],
                    created_at=float(r["created_at"]),
                )
                for r in rows
            ]

    def add_observation(
        self,
        session_id: str,
        step: int,
        cmd: str,
        raw_output: str,
        obs_id: str | None = None,
    ) -> ObservationRecord:
        with self._connect() as conn:
            if obs_id is None:
                count_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM observations WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                next_idx = (int(count_row["cnt"]) if count_row else 0) + 1
                obs_id = f"obs_{next_idx}"

            char_len = len(raw_output)
            cmd_short = cmd.strip().replace("\n", " ")[:48]
            summary = (
                f"[{obs_id} folded: `{cmd_short}` ({char_len:,} chars) | "
                f"use `mem search <q>` or `mem recall {obs_id}`]"
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO observations (
                    id, session_id, step, cmd, raw_output, summary, char_len
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (obs_id, session_id, step, cmd, raw_output, summary, char_len),
            )
        # Index observation chunks into FTS5
        self.index_text(session_id, "observation", obs_id, raw_output)
        return ObservationRecord(
            id=obs_id,
            session_id=session_id,
            step=step,
            cmd=cmd,
            raw_output=raw_output,
            summary=summary,
            char_len=char_len,
        )

    def get_observation(self, session_id: str, obs_id: str) -> ObservationRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM observations WHERE session_id = ? AND id = ?",
                (session_id, obs_id),
            ).fetchone()
            if not row:
                return None
            return ObservationRecord(
                id=str(row["id"]),
                session_id=str(row["session_id"]),
                step=int(row["step"]),
                cmd=str(row["cmd"]),
                raw_output=str(row["raw_output"]),
                summary=str(row["summary"]),
                char_len=int(row["char_len"]),
            )

    def list_observations(self, session_id: str) -> dict[str, ObservationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM observations WHERE session_id = ? ORDER BY step ASC",
                (session_id,),
            ).fetchall()
            return {
                str(r["id"]): ObservationRecord(
                    id=str(r["id"]),
                    session_id=str(r["session_id"]),
                    step=int(r["step"]),
                    cmd=str(r["cmd"]),
                    raw_output=str(r["raw_output"]),
                    summary=str(r["summary"]),
                    char_len=int(r["char_len"]),
                )
                for r in rows
            }

    def set_pin(self, session_id: str, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pins (session_id, key, value) VALUES (?, ?, ?)",
                (session_id, key, value),
            )
        self.index_text(session_id, "pin", key, f"{key}: {value}")

    def remove_pin(self, session_id: str, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM pins WHERE session_id = ? AND key = ?",
                (session_id, key),
            )
            conn.execute(
                "DELETE FROM chunks_fts "
                "WHERE session_id = ? AND source_type = 'pin' AND source_id = ?",
                (session_id, key),
            )
            return (cur.rowcount or 0) > 0

    def get_pins(self, session_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM pins WHERE session_id = ? ORDER BY key ASC",
                (session_id,),
            ).fetchall()
            return {str(r["key"]): str(r["value"]) for r in rows}

    def enqueue_inbox(self, session_id: str, message: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO inbox (session_id, message, consumed, created_at) VALUES (?, ?, 0, ?)",
                (session_id, message, time.time()),
            )
            return int(cur.lastrowid or 0)

    def consume_inbox(self, session_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, message FROM inbox "
                "WHERE session_id = ? AND consumed = 0 ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            if not rows:
                return []
            ids = [int(r["id"]) for r in rows]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE inbox SET consumed = 1 WHERE id IN ({placeholders})",
                tuple(ids),
            )
            return [str(r["message"]) for r in rows]

    def index_text(
        self,
        session_id: str,
        source_type: str,
        source_id: str,
        text: str,
        max_chunk_chars: int = 600,
    ) -> int:
        """Chunk and index text into the SQLite FTS5 `chunks_fts` table."""
        chunks = chunk_text(text, max_chars=max_chunk_chars)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM chunks_fts WHERE session_id = ? AND source_type = ? AND source_id = ?",
                (session_id, source_type, source_id),
            )
            for idx, chunk in enumerate(chunks):
                conn.execute(
                    """
                    INSERT INTO chunks_fts (
                        session_id, source_type, source_id, chunk_index, content
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, source_type, source_id, idx, chunk),
                )
        return len(chunks)

    def search_chunks(
        self,
        query: str,
        session_ids: list[str],
        source_types: list[str] | None = None,
        source_id: str | None = None,
        top_k: int = 3,
    ) -> list[ChunkHit]:
        """Run a BM25-ranked FTS5 query across the specified session(s)."""
        if not session_ids:
            return []
        tokens = _sanitize_fts_tokens(query)
        if not tokens:
            return []

        session_placeholders = ",".join("?" for _ in session_ids)
        where_clauses = [f"session_id IN ({session_placeholders})"]
        base_params: list[Any] = list(session_ids)

        if source_types:
            st_placeholders = ",".join("?" for _ in source_types)
            where_clauses.append(f"source_type IN ({st_placeholders})")
            base_params.extend(source_types)

        if source_id:
            where_clauses.append("source_id = ?")
            base_params.append(source_id)

        where_sql = " AND ".join(where_clauses)

        # Try strict AND match first, then fallback to OR match if empty
        candidate_expressions = [" ".join(tokens)]
        if len(tokens) > 1:
            candidate_expressions.append(" OR ".join(tokens))

        with self._connect() as conn:
            for fts_expr in candidate_expressions:
                sql = f"""
                    SELECT session_id, source_type, source_id, chunk_index, content,
                           bm25(chunks_fts) AS score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ? AND {where_sql}
                    ORDER BY score ASC
                    LIMIT ?
                """
                params = [fts_expr, *base_params, top_k]
                rows = conn.execute(sql, tuple(params)).fetchall()
                if rows:
                    return [
                        ChunkHit(
                            session_id=str(r["session_id"]),
                            source_type=str(r["source_type"]),
                            source_id=str(r["source_id"]),
                            chunk_index=int(r["chunk_index"]),
                            content=str(r["content"]),
                            score=float(r["score"]),
                        )
                        for r in rows
                    ]
        return []

    def get_session_digest(self, session_id: str) -> str:
        """Build a compact ~50-token digest card for a session (avoids flooding parent context)."""
        session = self.get_session(session_id)
        if not session:
            return f"Error: session `{session_id}` not found."

        with self._connect() as conn:
            chunk_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM chunks_fts WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            obs_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM observations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            chunk_count = int(chunk_row["cnt"]) if chunk_row else 0
            obs_count = int(obs_row["cnt"]) if obs_row else 0

        res_text = session.result or ""
        char_len = len(res_text)
        preview_lines = [line.strip() for line in res_text.splitlines() if line.strip()][:2]
        preview = " | ".join(preview_lines)[:160]
        if len(res_text) > 160:
            preview += "..."

        lines = [
            f"[{session.id} {session.status} | steps: {session.step_count}/{session.max_steps} | "
            f"{char_len:,} chars, {chunk_count} chunks, {obs_count} obs]"
        ]
        if preview:
            lines.append(f"Preview: {preview}")
        if chunk_count > 0:
            lines.append(
                f'Hint: run `agent query {session.id} "<keywords>"` for BM25 RAG snippets, '
                f"or `agent read {session.id} --full`."
            )
        return "\n".join(lines)
