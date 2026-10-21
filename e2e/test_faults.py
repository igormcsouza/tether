"""Infrastructure failures: the envelope must self-heal or fail loudly, whatever the model."""

from __future__ import annotations

import os
import signal
import sqlite3
import time
from pathlib import Path

from e2e.conftest import Tether


def test_429_is_retried_honoring_retry_after(tmp_path: Path, chaos, model: str) -> None:
    chaos.fault("status", times=2, code=429, retry_after=1)
    t = Tether(tmp_path, chaos, model)
    r = t.run("Reply ok then finish.", "--max-steps", "6")
    assert len(chaos.requests) >= 3, "the two 429s must be retried, not fatal"
    assert r["failure"] is None or r["failure"]["kind"] != "worker_error", r


def test_persistent_5xx_fails_loudly_with_exit_5(tether: Tether, chaos) -> None:
    chaos.fault("status", times=10, code=503)
    r = tether.run("anything")
    assert (r["rc"], r["status"]) == (5, "FAILED")
    assert "unavailable after 3 attempts" in r["failure"]["message"]


def test_trickling_response_hits_the_per_attempt_deadline(tmp_path: Path, chaos) -> None:
    """#88: bytes keep arriving so httpx's read timeout never fires; the deadline must."""
    chaos.fault("trickle", times=3, seconds=60)
    t = Tether(tmp_path, chaos, timeout=3)
    start = time.time()
    r = t.run("anything")
    assert (r["rc"], r["status"]) == (5, "FAILED")
    assert "TimeoutError" in r["failure"]["message"], r["failure"]
    assert time.time() - start < 40, "must not hang past attempts x timeout"


def test_auth_error_names_the_variable_never_the_value(tether: Tether, chaos) -> None:
    r = tether.run("anything", prefix="e2eauth")
    assert r["rc"] == 5 and "E2E_KEY" in r["failure"]["message"]
    assert "sekret-value-123" not in r["failure"]["message"] + r["stderr"]


def test_killed_worker_is_reported_failed_not_running(tether: Tether, chaos) -> None:
    """#85: kill -9 the headless worker; status/list must flip RUNNING to FAILED."""
    chaos.stall_all = 120  # the worker sits inside a model call
    sid = tether.cli("run", "--headless", "--model", "e2e/scripted", "go").stdout.strip()
    db = tether.ws / ".tether" / "tether.db"
    for _ in range(100):
        row = (
            sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            .execute("select status, pid from sessions where id=?", (sid,))
            .fetchone()
        )
        if row and row[0] == "RUNNING" and row[1]:
            break
        time.sleep(0.2)
    else:
        raise AssertionError(f"worker never reached RUNNING: {row}")
    os.kill(row[1], signal.SIGKILL)
    time.sleep(0.5)
    out = tether.cli("status", sid).stdout
    assert "FAILED" in out and "RUNNING" not in out, out
    assert "FAILED" in tether.cli("list").stdout
