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

GLOBAL_SESSION_ID = "__project__"
_FRICTION_EVENTS = (
    "loop_stall",
    "cycle_stall",
    "syntax_error",
    "tool_error",
    "gate_fail",
    "gate_error",
)


@dataclass(slots=True)
class SessionRecord:
    id: str
    parent_id: str | None
    status: str  # PENDING | RUNNING | WAITING_INPUT | COMPLETED | FAILED
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
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


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
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int = 0
    event_type: str = "ok"


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


@dataclass(slots=True)
class ModelStats:
    model: str
    runs: int
    completed_runs: int
    pass_rate: float
    avg_steps: float
    avg_peak_tokens: int
    max_peak_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    avg_total_tokens: int
    avg_duration_ms: int
    nudges: int
    loop_stalls: int
    cycle_stalls: int
    syntax_errors: int
    tool_errors: int
    gate_fails: int
    gate_errors: int
    avg_nudges: float
    avg_loop_stalls: float
    avg_syntax_errors: float


@dataclass(slots=True)
class ToolOffender:
    command: str
    syntax_errors: int
    loop_stalls: int
    cycle_stalls: int
    tool_errors: int
    gate_errors: int
    total_friction: int


@dataclass(slots=True)
class StatsReport:
    models: list[ModelStats]
    offenders: list[ToolOffender]


_SUBCOMMAND_TOOLS: dict[str, set[str]] = {
    "edit": {"view", "write", "replace"},
    "web": {"search", "fetch"},
    "mem": {"pin", "unpin", "list", "search", "recall"},
    "agent": {"spawn", "status", "wait", "query", "read", "send"},
    "skill": {"list", "load"},
}


def canonical_tool_command(raw_cmd: str | None) -> str:
    """Normalize a raw tool command into its canonical `<tool>` or `<tool> <subcommand>` key."""
    if not raw_cmd:
        return "unknown"
    cleaned = raw_cmd.strip().strip("`").lstrip("$>").strip()
    if cleaned.startswith("tether "):
        cleaned = cleaned[len("tether ") :].strip()
    tokens = [tok.strip("\"'") for tok in cleaned.split() if tok.strip("\"'")]
    if not tokens:
        return "unknown"
    head = tokens[0]
    if head in _SUBCOMMAND_TOOLS and len(tokens) >= 2 and tokens[1] in _SUBCOMMAND_TOOLS[head]:
        return f"{head} {tokens[1]}"
    return head


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
                    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
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
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    event_type TEXT NOT NULL DEFAULT 'ok',
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
            self._ensure_columns(
                conn,
                "sessions",
                {
                    "total_prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "total_completion_tokens": "INTEGER NOT NULL DEFAULT 0",
                },
            )
            self._ensure_columns(
                conn,
                "turns",
                {
                    "prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "completion_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "duration_ms": "INTEGER NOT NULL DEFAULT 0",
                    "event_type": "TEXT NOT NULL DEFAULT 'ok'",
                },
            )

    @staticmethod
    def _ensure_columns(
        conn: sqlite3.Connection,
        table: str,
        columns: dict[str, str],
    ) -> None:
        existing = {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_def in columns.items():
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")

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
            total_prompt_tokens=int(row["total_prompt_tokens"]),
            total_completion_tokens=int(row["total_completion_tokens"]),
        )

    @staticmethod
    def _row_to_turn(row: sqlite3.Row) -> TurnRecord:
        return TurnRecord(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            step=int(row["step"]),
            role=str(row["role"]),
            content=str(row["content"]),
            tool_cmd=row["tool_cmd"],
            tool_stdin=row["tool_stdin"],
            obs_id=row["obs_id"],
            created_at=float(row["created_at"]),
            prompt_tokens=int(row["prompt_tokens"]),
            completion_tokens=int(row["completion_tokens"]),
            duration_ms=int(row["duration_ms"]),
            event_type=str(row["event_type"]),
        )

    def _reap_dead(self, rec: SessionRecord) -> SessionRecord:
        """If rec is RUNNING with a pid that no longer exists, mark it FAILED and re-read."""
        if rec.status == "RUNNING" and rec.pid is not None:
            try:
                os.kill(rec.pid, 0)
            except PermissionError:  # alive, owned by another user
                return rec
            except ProcessLookupError:
                self.update_session(
                    rec.id,
                    status="FAILED",
                    result=f"Worker died (pid {rec.pid}) before finishing",
                )
                # Re-read the updated record
                with self._connect() as conn:
                    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (rec.id,)).fetchone()
                    return self._row_to_session(row) if row else rec
        return rec

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            rec = self._row_to_session(row) if row else None
        return self._reap_dead(rec) if rec else None

    def list_sessions(self, parent_id: str | None = None, limit: int = 50) -> list[SessionRecord]:
        with self._connect() as conn:
            if parent_id is not None:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE parent_id = ? "
                    "ORDER BY created_at ASC, rowid ASC LIMIT ?",
                    (parent_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            records = [self._row_to_session(r) for r in rows]
        return [self._reap_dead(rec) for rec in records]

    def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        model: str | None = None,
        result: str | None = None,
        step_count: int | None = None,
        peak_tokens: int | None = None,
        add_prompt_tokens: int | None = None,
        add_completion_tokens: int | None = None,
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
        if add_prompt_tokens is not None:
            updates.append("total_prompt_tokens = total_prompt_tokens + ?")
            params.append(add_prompt_tokens)
        if add_completion_tokens is not None:
            updates.append("total_completion_tokens = total_completion_tokens + ?")
            params.append(add_completion_tokens)
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
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_ms: int = 0,
        event_type: str = "ok",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO turns (
                    session_id, step, role, content, tool_cmd, tool_stdin, obs_id,
                    prompt_tokens, completion_tokens, duration_ms, event_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    step,
                    role,
                    content,
                    tool_cmd,
                    tool_stdin,
                    obs_id,
                    prompt_tokens,
                    completion_tokens,
                    duration_ms,
                    event_type,
                    time.time(),
                ),
            )
            return int(cur.lastrowid or 0)

    def update_turn_telemetry(
        self,
        turn_id: int,
        *,
        event_type: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if event_type is not None:
            updates.append("event_type = ?")
            params.append(event_type)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            params.append(duration_ms)
        if not updates:
            return
        params.append(turn_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE turns SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )

    def get_turns(self, session_id: str) -> list[TurnRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY id ASC", (session_id,)
            ).fetchall()
            return [self._row_to_turn(r) for r in rows]

    def list_nudges(
        self, session_id: str | None = None, model: str | None = None, limit: int = 20
    ) -> list[tuple[SessionRecord, TurnRecord]]:
        """Most recent assistant replies the harness could not parse (newest first)."""
        sql = (
            "SELECT t.* FROM turns t JOIN sessions s ON s.id = t.session_id "
            "WHERE t.role = 'assistant' AND t.event_type = 'nudge'"
        )
        params: list[Any] = []
        if session_id is not None:
            sql += " AND t.session_id = ?"
            params.append(session_id)
        if model is not None:
            sql += " AND s.model = ?"
            params.append(model)
        sql += " ORDER BY t.id DESC LIMIT ?"
        params.append(limit)
        out: list[tuple[SessionRecord, TurnRecord]] = []
        with self._connect() as conn:
            for row in conn.execute(sql, tuple(params)).fetchall():
                srow = conn.execute(
                    "SELECT * FROM sessions WHERE id = ?", (row["session_id"],)
                ).fetchone()
                out.append((self._row_to_session(srow), self._row_to_turn(row)))
        return out

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

    def get_project_session_ids(self) -> list[str]:
        """Return GLOBAL_SESSION_ID plus all COMPLETED session IDs for cross-session RAG."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE status = 'COMPLETED' ORDER BY updated_at DESC"
            ).fetchall()
            completed_ids = [str(r["id"]) for r in rows if str(r["id"]) != GLOBAL_SESSION_ID]
            return [GLOBAL_SESSION_ID, *completed_ids]

    def search_project_chunks(
        self,
        query: str,
        *,
        source_types: list[str] | None = None,
        source_id: str | None = None,
        top_k: int = 3,
    ) -> list[ChunkHit]:
        """Run a BM25 FTS5 query across project pins (`__project__`) and COMPLETED sessions."""
        return self.search_chunks(
            query,
            session_ids=self.get_project_session_ids(),
            source_types=source_types,
            source_id=source_id,
            top_k=top_k,
        )

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
        if session.status == "WAITING_INPUT":
            lines.append(
                f"Hint: session is waiting for input; reply via "
                f'`agent send {session.id} "<answer>"` or `tether send {session.id} "<answer>"`.'
            )
        elif chunk_count > 0:
            lines.append(
                f'Hint: run `agent query {session.id} "<keywords>"` for BM25 RAG snippets, '
                f"or `agent read {session.id} --full`."
            )
        return "\n".join(lines)

    def extract_friction_trace(self, session_id: str) -> list[str]:
        """Deterministic `failed -> correction/fix` lines from a session's turns (for `retro`)."""
        turns = self.get_turns(session_id)
        trace: list[str] = []
        for i, t in enumerate(turns):
            if t.role == "user" and t.content.startswith("[Follow-up instruction]:"):
                trace.append(f"correction: {t.content.split(':', 1)[1].strip()[:200]}")
            elif t.role == "assistant" and t.event_type in _FRICTION_EVENTS:
                err = next(
                    (x.content for x in turns[i + 1 :] if x.role == "tool" and x.step == t.step),
                    "",
                )
                line = f"failed[{t.event_type}]: `{(t.tool_cmd or '').strip()[:100]}`"
                if err:
                    line += f" -> {err.strip()[:150]}"
                fix = next(
                    (
                        x.tool_cmd
                        for x in turns[i + 1 :]
                        if x.role == "assistant" and x.event_type in ("ok", "completed")
                    ),
                    None,
                )
                if fix:
                    line += f" | then: `{fix.strip()[:100]}`"
                trace.append(line)
        return trace

    def get_stats(
        self,
        *,
        model: str | None = None,
        skill: str | None = None,
        limit: int = 100,
    ) -> StatsReport:
        """Aggregate per-model telemetry, token cost, and ACI friction offenders."""
        where_clauses = ["id != ?"]
        params: list[Any] = [GLOBAL_SESSION_ID]
        if model:
            where_clauses.append("model = ?")
            params.append(model)
        if skill:
            where_clauses.append("skill = ?")
            params.append(skill)
        params.append(limit)

        where_sql = " AND ".join(where_clauses)
        with self._connect() as conn:
            session_rows = conn.execute(
                f"SELECT * FROM sessions WHERE {where_sql} ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            # Pipeline root rows only roll up their stage sessions: counting them would
            # double-count tokens and invent a run for a model that never executed.
            sessions = [
                s
                for s in (self._row_to_session(r) for r in session_rows)
                if "pipeline" not in s.sandbox_config
            ]
            if not sessions:
                return StatsReport(models=[], offenders=[])
            session_ids = [s.id for s in sessions]
            placeholders = ",".join("?" for _ in session_ids)
            turn_rows = conn.execute(
                f"SELECT * FROM turns WHERE session_id IN ({placeholders}) ORDER BY id ASC",
                tuple(session_ids),
            ).fetchall()
            turns = [self._row_to_turn(r) for r in turn_rows]

        turns_by_session: dict[str, list[TurnRecord]] = {sid: [] for sid in session_ids}
        for t in turns:
            turns_by_session[t.session_id].append(t)

        sessions_by_model: dict[str, list[SessionRecord]] = {}
        for s in sessions:
            sessions_by_model.setdefault(s.model, []).append(s)

        model_stats: list[ModelStats] = []
        for model_name, msessions in sessions_by_model.items():
            runs = len(msessions)
            completed_runs = sum(1 for s in msessions if s.status == "COMPLETED")
            pass_rate = (completed_runs / runs) * 100.0
            avg_steps = sum(s.step_count for s in msessions) / runs
            avg_peak = int(round(sum(s.peak_tokens for s in msessions) / runs))
            max_peak = max(s.peak_tokens for s in msessions)
            tot_prompt = sum(s.total_prompt_tokens for s in msessions)
            tot_comp = sum(s.total_completion_tokens for s in msessions)
            tot_tok = tot_prompt + tot_comp
            avg_tot_tok = int(round(tot_tok / runs))

            mturns = [t for s in msessions for t in turns_by_session[s.id]]
            tot_dur = sum(t.duration_ms for t in mturns)
            avg_dur = int(round(tot_dur / runs))
            nudges = sum(1 for t in mturns if t.event_type == "nudge")
            loops = sum(1 for t in mturns if t.event_type == "loop_stall")
            cycles = sum(1 for t in mturns if t.event_type == "cycle_stall")
            syn_err = sum(1 for t in mturns if t.event_type == "syntax_error")
            tool_err = sum(1 for t in mturns if t.event_type == "tool_error")
            gate_fail = sum(1 for t in mturns if t.event_type == "gate_fail")
            gate_err = sum(1 for t in mturns if t.event_type == "gate_error")

            model_stats.append(
                ModelStats(
                    model=model_name,
                    runs=runs,
                    completed_runs=completed_runs,
                    pass_rate=pass_rate,
                    avg_steps=avg_steps,
                    avg_peak_tokens=avg_peak,
                    max_peak_tokens=max_peak,
                    total_prompt_tokens=tot_prompt,
                    total_completion_tokens=tot_comp,
                    total_tokens=tot_tok,
                    avg_total_tokens=avg_tot_tok,
                    avg_duration_ms=avg_dur,
                    nudges=nudges,
                    loop_stalls=loops,
                    cycle_stalls=cycles,
                    syntax_errors=syn_err,
                    tool_errors=tool_err,
                    gate_fails=gate_fail,
                    gate_errors=gate_err,
                    avg_nudges=nudges / runs,
                    avg_loop_stalls=loops / runs,
                    avg_syntax_errors=syn_err / runs,
                )
            )

        model_stats.sort(key=lambda m: (-m.runs, m.model))

        offenders_by_cmd: dict[str, ToolOffender] = {}
        for t in turns:
            if t.event_type in (
                "syntax_error",
                "loop_stall",
                "cycle_stall",
                "tool_error",
                "gate_error",
            ):
                cmd_key = canonical_tool_command(t.tool_cmd)
                off = offenders_by_cmd.get(cmd_key)
                if off is None:
                    off = ToolOffender(
                        command=cmd_key,
                        syntax_errors=0,
                        loop_stalls=0,
                        cycle_stalls=0,
                        tool_errors=0,
                        gate_errors=0,
                        total_friction=0,
                    )
                    offenders_by_cmd[cmd_key] = off
                if t.event_type == "syntax_error":
                    off.syntax_errors += 1
                elif t.event_type == "loop_stall":
                    off.loop_stalls += 1
                elif t.event_type == "cycle_stall":
                    off.cycle_stalls += 1
                elif t.event_type == "gate_error":
                    off.gate_errors += 1
                else:
                    off.tool_errors += 1
                off.total_friction += 1

        offenders = sorted(
            offenders_by_cmd.values(),
            key=lambda o: (-o.total_friction, -o.syntax_errors, -o.loop_stalls, o.command),
        )
        return StatsReport(models=model_stats, offenders=offenders)

    def format_stats_report(
        self,
        *,
        model: str | None = None,
        skill: str | None = None,
        limit: int = 100,
    ) -> str:
        """Render the ultra-compact `tether stats` engineering scorecard and top offenders."""
        report = self.get_stats(model=model, skill=skill, limit=limit)
        if not report.models:
            return "No sessions recorded."

        lines = [
            f"{'MODEL':<21} {'RUNS':>4} {'PASS%':>6} {'AVG_STEPS':>9} "
            f"{'PEAK_TOK':>8} {'TOTAL_TOK':>9} {'NUDGES':>6} {'LOOPS':>5} "
            f"{'CYCLES':>6} {'SYNTAX_ERR':>10} {'GATE_ERR':>8}"
        ]
        for m in report.models:
            pass_str = f"{m.pass_rate:.1f}%"
            lines.append(
                f"{m.model:<21} {m.runs:>4} {pass_str:>6} {m.avg_steps:>9.1f} "
                f"{m.avg_peak_tokens:>8} {m.avg_total_tokens:>9} "
                f"{m.avg_nudges:>6.1f} {m.avg_loop_stalls:>5.1f} {m.cycle_stalls:>6} "
                f"{m.avg_syntax_errors:>10.1f} {m.gate_errors:>8}"
            )

        if report.offenders:
            lines.append("")
            lines.append("Top Friction Offenders (by command):")
            lines.append(
                f"{'COMMAND':<21} {'SYNTAX_ERR':>10} {'LOOPS':>5} {'CYCLES':>6} "
                f"{'TOOL_ERR':>8} {'GATE_ERR':>8} {'TOTAL':>5}"
            )
            for off in report.offenders:
                lines.append(
                    f"{off.command:<21} {off.syntax_errors:>10} {off.loop_stalls:>5} "
                    f"{off.cycle_stalls:>6} {off.tool_errors:>8} {off.gate_errors:>8} "
                    f"{off.total_friction:>5}"
                )
        return "\n".join(lines)
