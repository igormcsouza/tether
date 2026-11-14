"""F3 last-step notice: a scripted lookup-only session is told on its last-but-one step to answer.

Scripted replies, so the result never depends on the model.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_last_step_notice_reaches_a_lookup_only_session(tether: Tether, chaos) -> None:
    # 9 lookups within 10 steps: the notice lands on step 9, the one before the limit
    chaos.script(*[f"ls {i}" for i in range(9)])
    r = tether.run("look around", "--tools", "bash", "--max-steps", "10")
    outs = tether.tool_outputs(r["id"])
    notices = [o for o in outs if "[LAST STEP]" in o]
    assert len(notices) == 1, outs[-3:]
    assert "Call `done` now with your answer" in notices[0]
    assert r["rc"] in (0, 2), r
