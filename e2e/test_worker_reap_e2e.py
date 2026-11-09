"""#271: a dead PENDING worker leaves a FAILED session naming its log (scripted)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys

from e2e.conftest import Tether


def _cli(t: Tether, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-P", "-m", "tether.cli", *args],
        cwd=t.ws,
        env=t.env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _dead_pid() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def test_dead_pending_worker_is_failed_with_log(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    p = _cli(tether, "run", "--headless", "--model", "e2e/scripted", "go")
    sid = p.stdout.strip()
    assert p.returncode == 0 and sid.startswith("ses_"), p.stderr
    assert _cli(tether, "wait", sid).returncode == 0

    dead = _dead_pid()
    db = tether.ws / ".tether" / "tether.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE sessions SET status='PENDING', pid=?, result=NULL WHERE id=?", (dead, sid)
        )

    assert "FAILED" in _cli(tether, "status", sid).stdout
    result = _cli(tether, "read", sid).stdout
    assert f"Worker died (pid {dead}) before starting" in result, result
    assert f"workers/{sid}.log" in result, result
