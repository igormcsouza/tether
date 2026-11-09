"""A PENDING headless worker that dies before starting must not leave its session PENDING (#271)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from tether import harness
from tether.store import SQLiteStore


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def _pending_session(store: SQLiteStore, pid: int | None) -> str:
    session = store.create_session("Test goal")
    if pid is None:
        store.update_session(session.id, status="PENDING")
    else:
        store.update_session(session.id, status="PENDING", pid=pid)
    return session.id


def test_pending_dead_pid_is_reaped(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    dead = _dead_pid()
    sid = _pending_session(store, dead)

    rec = store.get_session(sid)
    assert rec is not None
    assert rec.status == "FAILED"
    assert rec.result == f"Worker died (pid {dead}) before starting"

    listed = {r.id: r for r in store.list_sessions()}
    assert listed[sid].status == "FAILED"
    assert listed[sid].result == f"Worker died (pid {dead}) before starting"


def test_pending_without_pid_not_reaped(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    sid = _pending_session(store, None)

    rec = store.get_session(sid)
    assert rec is not None
    assert rec.status == "PENDING"
    assert rec.pid is None


def test_pending_live_pid_not_reaped(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    sid = _pending_session(store, os.getpid())

    rec = store.get_session(sid)
    assert rec is not None
    assert rec.status == "PENDING"


def test_pending_permission_error_not_reaped(tmp_path: Path, monkeypatch: Any) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    sid = _pending_session(store, _dead_pid())

    def _other_user(pid: int, sig: int) -> None:
        raise PermissionError(pid)

    monkeypatch.setattr(os, "kill", _other_user)
    rec = store.get_session(sid)
    assert rec is not None
    assert rec.status == "PENDING"


def test_completed_session_with_dead_pid_untouched(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    session = store.create_session("Test goal")
    store.update_session(session.id, status="COMPLETED", pid=_dead_pid(), result="ok")

    rec = store.get_session(session.id)
    assert rec is not None
    assert rec.status == "COMPLETED"
    assert rec.result == "ok"


def test_reaped_result_names_log(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    dead = _dead_pid()
    sid = _pending_session(store, dead)
    log = store.db_path.parent / "workers" / f"{sid}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("ModuleNotFoundError: no module named tether\n")

    rec = store.get_session(sid)
    assert rec is not None
    assert rec.status == "FAILED"
    assert rec.result == f"Worker died (pid {dead}) before starting (see {log})"


def test_pending_dead_pid_memory_store_has_no_log() -> None:
    store = SQLiteStore(db_path=":memory:")
    dead = _dead_pid()
    sid = _pending_session(store, dead)

    rec = store.get_session(sid)
    assert rec is not None
    assert rec.status == "FAILED"
    assert rec.result == f"Worker died (pid {dead}) before starting"


class _FakeProc:
    pid = 4242


def test_spawn_logs_worker_output(tmp_path: Path, monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_popen(argv: list[str], **kwargs: Any) -> _FakeProc:
        seen.update(kwargs)
        return _FakeProc()

    monkeypatch.setattr(harness.subprocess, "Popen", fake_popen)
    pid = harness.spawn_detached_worker(tmp_path / "tether.db", "sess-1")

    assert pid == 4242
    assert seen["stderr"] == subprocess.STDOUT
    out = seen["stdout"]
    assert hasattr(out, "name")
    expected = (tmp_path / "workers" / "sess-1.log").resolve()
    assert Path(out.name).resolve() == expected
    assert expected.parent.is_dir()
    assert "a" in out.mode
    out.close()
