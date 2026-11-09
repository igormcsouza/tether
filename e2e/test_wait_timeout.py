"""`tether wait` timeout (#269): an expired wait with a RUNNING session exits 6.

Scripted: the proxy plays the model, tether is real.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_wait_timeout_exits_6_while_session_running(tether: Tether, chaos) -> None:
    chaos.script(*[("bash sleep 5",)] * 20)
    r = tether.run("slow task", "--headless", "--tools", "bash")
    sid = r["id"]
    res = tether.cli("wait", sid, "--timeout", "0.5")
    assert res.returncode == 6, res.stderr
    assert f"timed out; still RUNNING: {sid}" in res.stderr
