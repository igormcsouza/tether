"""Machine-readable session view shared by `--json` CLI output and the MCP server.

Schema version 1. Keys are stable; new keys may be added, existing ones never change meaning.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from tether.store import SessionRecord, SQLiteStore

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_WAITING = 2
EXIT_GATE = 3
EXIT_MAX_STEPS = 4
EXIT_ERROR = 5

EXIT_CODES = {
    "completed": EXIT_OK,
    "usage": EXIT_USAGE,
    "waiting_input": EXIT_WAITING,
    "gate": EXIT_GATE,
    "max_steps": EXIT_MAX_STEPS,
    "worker_error": EXIT_ERROR,
}


def failure_info(rec: SessionRecord) -> dict[str, Any] | None:
    """Classify a FAILED session from its stored result text (None for any other status)."""
    if rec.status != "FAILED":
        return None
    msg = rec.result or ""
    if msg.startswith("Verification gate"):
        m = re.match(r"Verification gate `(.*)` (?:failed|misconfigured)", msg)
        return {"kind": "gate", "gate": m.group(1) if m else None, "message": msg}
    if msg.startswith("Max steps"):
        return {"kind": "max_steps", "gate": None, "message": msg}
    return {"kind": "worker_error", "gate": None, "message": msg or "unknown failure"}


def exit_code(rec: SessionRecord) -> int:
    """Map a session to a documented process exit code."""
    if rec.status == "WAITING_INPUT":
        return EXIT_WAITING
    fail = failure_info(rec)
    if fail:
        return EXIT_CODES[fail["kind"]]
    return EXIT_OK


def session_dict(rec: SessionRecord, *, include_result: bool = True) -> dict[str, Any]:
    """Stable JSON view of a session. `result` holds the deliverable or the pending question."""
    fail = failure_info(rec)
    out: dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "id": rec.id,
        "status": rec.status,
        "model": rec.model,
        "steps": rec.step_count,
        "max_steps": rec.max_steps,
        "tokens": {
            "prompt": rec.total_prompt_tokens,
            "completion": rec.total_completion_tokens,
        },
        "duration_ms": int(max(0.0, rec.updated_at - rec.created_at) * 1000),
        "failure": fail,
        "exit_code": exit_code(rec),
    }
    if include_result:
        # A failure reason is not a deliverable: it lives under `failure` only.
        out["result"] = None if fail else rec.result
    return out


def digest_dict(store: SQLiteStore, rec: SessionRecord) -> dict[str, Any]:
    d = session_dict(rec, include_result=False)
    d["digest"] = store.get_session_digest(rec.id)
    return d


def events(store: SQLiteStore, session_id: str, after_turn: int = 0) -> list[dict[str, Any]]:
    """Turn-level events for `tether events` (JSONL) and MCP `tether_read` steps."""
    out: list[dict[str, Any]] = []
    for t in store.get_turns(session_id):
        if t.id <= after_turn:
            continue
        out.append(
            {
                "turn": t.id,
                "step": t.step,
                "role": t.role,
                "cmd": t.tool_cmd,
                "event": t.event_type,
                "text": (t.content or "")[:200],
            }
        )
    return out


def stats_dict(store: SQLiteStore, **kw: Any) -> dict[str, Any]:
    rep = store.get_stats(**kw)
    return {
        "v": SCHEMA_VERSION,
        "models": [dataclasses.asdict(m) for m in rep.models],
        "offenders": [dataclasses.asdict(o) for o in rep.offenders],
    }
