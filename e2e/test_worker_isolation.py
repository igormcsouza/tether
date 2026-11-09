"""#273: a workspace's own tether/ package must never run inside the headless worker (scripted).

The parent CLI is started with -P here so that only the worker spawn is under test.
"""

from __future__ import annotations

import subprocess
import sys

from e2e.conftest import Tether

SHADOW = "raise RuntimeError('shadowed')\n"


def _cli(t: Tether, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-P", "-m", "tether.cli", *args],
        cwd=t.ws,
        env=t.env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_headless_worker_ignores_workspace_tether_package(tether: Tether, chaos) -> None:
    (tether.ws / "tether").mkdir()
    (tether.ws / "tether" / "__init__.py").write_text(SHADOW)
    chaos.script(("done", "installed tether ran"))
    p = _cli(tether, "run", "--headless", "--model", "e2e/scripted", "go")
    sid = p.stdout.strip()
    assert p.returncode == 0 and sid.startswith("ses_"), p.stderr
    assert _cli(tether, "wait", sid).returncode == 0
    assert _cli(tether, "read", sid).stdout.strip() == "installed tether ran"
    assert "COMPLETED" in _cli(tether, "status", sid).stdout
