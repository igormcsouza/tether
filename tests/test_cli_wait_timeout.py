"""Tests for `tether wait` timeout behaviour (#269)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tether import SQLiteStore, api
from tether.cli import _async_main

EXIT_WAIT_TIMEOUT = 6
TIMEOUT_PREFIX = "timed out; still RUNNING: "


def _store(tmp_path: Path, name: str) -> tuple[SQLiteStore, str]:
    db_file = tmp_path / name
    return SQLiteStore(db_path=db_file), str(db_file)


async def test_help_shows_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD-1: `tether wait --help` shows the default timeout in seconds."""
    monkeypatch.setenv("COLUMNS", "200")
    with pytest.raises(SystemExit) as exc:
        await _async_main(["wait", "--help"])
    assert exc.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "default: 120 seconds" in out


async def test_timeout_exits_nonzero_and_names_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD-2: expired wait with a RUNNING session exits 6 and names the id on stderr."""
    store, db = _store(tmp_path, "timeout.db")
    rec = store.create_session("Running session")
    store.update_session(rec.id, status="RUNNING")

    code = await _async_main(["wait", rec.id, "--timeout", "0.2", "--db", db])

    assert code == EXIT_WAIT_TIMEOUT
    assert capsys.readouterr().err.strip() == f"{TIMEOUT_PREFIX}{rec.id}"


async def test_pending_counts_as_still(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Bad-day: a PENDING session at timeout is listed and exits 6."""
    store, db = _store(tmp_path, "pending.db")
    rec = store.create_session("Pending session")
    store.update_session(rec.id, status="PENDING")

    code = await _async_main(["wait", rec.id, "--timeout", "0.2", "--db", db])

    assert code == EXIT_WAIT_TIMEOUT
    assert capsys.readouterr().err.strip() == f"{TIMEOUT_PREFIX}{rec.id}"


async def test_mixed_lists_only_running(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Bad-day: COMPLETED + RUNNING at timeout exits 6 and lists only the RUNNING id."""
    store, db = _store(tmp_path, "mixed.db")
    done = store.create_session("Completed session")
    store.update_session(done.id, status="COMPLETED", result="done")
    running = store.create_session("Running session")
    store.update_session(running.id, status="RUNNING")

    code = await _async_main(["wait", done.id, running.id, "--timeout", "0.2", "--db", db])

    assert code == EXIT_WAIT_TIMEOUT
    err = capsys.readouterr().err
    assert err.strip() == f"{TIMEOUT_PREFIX}{running.id}"
    assert done.id not in err


async def test_waiting_input_early_break_is_not_a_timeout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad-day: WAITING_INPUT breaks the loop early; exit 2 and no timeout message."""
    store, db = _store(tmp_path, "waiting.db")
    waiting = store.create_session("Waiting session")
    store.update_session(waiting.id, status="WAITING_INPUT")
    running = store.create_session("Running session")
    store.update_session(running.id, status="RUNNING")

    code = await _async_main(["wait", waiting.id, running.id, "--timeout", "5.0", "--db", db])

    assert code == api.EXIT_WAITING
    assert "timed out" not in capsys.readouterr().err


async def test_unknown_id_not_counted_as_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad-day: an unknown session id is not reported as still running."""
    _, db = _store(tmp_path, "unknown.db")

    code = await _async_main(["wait", "ses_unknown", "--timeout", "0.2", "--db", db])

    assert code == 0
    assert "timed out" not in capsys.readouterr().err


async def test_unknown_and_running_lists_only_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad-day: unknown id + RUNNING id at timeout exits 6 and lists only the RUNNING id."""
    store, db = _store(tmp_path, "unknown_running.db")
    running = store.create_session("Running session")
    store.update_session(running.id, status="RUNNING")

    code = await _async_main(["wait", "ses_unknown", running.id, "--timeout", "0.2", "--db", db])

    assert code == EXIT_WAIT_TIMEOUT
    err = capsys.readouterr().err
    assert err.strip() == f"{TIMEOUT_PREFIX}{running.id}"
    assert "ses_unknown" not in err


async def test_finished_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """DoD-3: all sessions finish in time -> exit 0 and empty stderr."""
    store, db = _store(tmp_path, "finished.db")
    rec = store.create_session("Finished session")
    store.update_session(rec.id, status="COMPLETED", result="done")

    code = await _async_main(["wait", rec.id, "--timeout", "1.0", "--db", db])

    assert code == 0
    assert capsys.readouterr().err == ""


async def test_json_timeout_keeps_stdout_and_exits_6(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad-day: --json at timeout prints the JSON list on stdout, message on stderr, exit 6."""
    store, db = _store(tmp_path, "json.db")
    rec = store.create_session("Running session")
    store.update_session(rec.id, status="RUNNING")

    code = await _async_main(["wait", rec.id, "--timeout", "0.2", "--json", "--db", db])

    captured = capsys.readouterr()
    assert code == EXIT_WAIT_TIMEOUT
    assert captured.out.lstrip().startswith("[")
    assert rec.id in captured.out
    assert captured.err.strip() == f"{TIMEOUT_PREFIX}{rec.id}"


async def test_session_finishing_before_deadline_is_finished(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad-day: a session that completes before the deadline is reported as finished."""
    store, db = _store(tmp_path, "deadline.db")
    rec = store.create_session("Deadline session")
    store.update_session(rec.id, status="RUNNING")

    async def finish_soon() -> None:
        await asyncio.sleep(0.05)
        store.update_session(rec.id, status="COMPLETED", result="done")

    finisher = asyncio.create_task(finish_soon())
    code = await _async_main(["wait", rec.id, "--timeout", "2.0", "--db", db])
    await finisher

    assert code == 0
    assert "timed out" not in capsys.readouterr().err
