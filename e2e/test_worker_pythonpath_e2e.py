"""#283: a headless worker with empty and relative PYTHONPATH entries still runs (scripted)."""

from __future__ import annotations

import subprocess
import sys

from e2e.conftest import Tether


def _cli(t: Tether, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-P", "-m", "tether.cli", *args],
        cwd=t.ws,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_headless_run_survives_empty_and_relative_pythonpath(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    dirty = dict(tether.env)
    dirty["PYTHONPATH"] = ":."
    p = _cli(tether, dirty, "run", "--headless", "--model", "e2e/scripted", "go")
    sid = p.stdout.strip()
    assert p.returncode == 0 and sid.startswith("ses_"), p.stderr
    assert _cli(tether, tether.env, "wait", sid).returncode == 0
    r = _cli(tether, tether.env, "read", sid)
    assert "ok" in r.stdout, r.stdout + r.stderr
