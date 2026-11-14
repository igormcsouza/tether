"""#319: a timed-out background job says why. Scripted: the replies never depend on the model."""

from __future__ import annotations

from e2e.conftest import Tether

HINT = "A background job (`&`) keeps the command open."


def test_timed_out_background_job_says_why(tether: Tether, chaos) -> None:
    # one 30 s wait: the sandbox kills the job at the timeout; the result must carry the hint
    chaos.script(("bash sleep 60 & wait", None), ("done", "finished"))
    r = tether.run("background", "--tools", "bash", "--max-steps", "4")
    outputs = tether.tool_outputs(r["id"])
    assert any("command timed out" in o and HINT in o for o in outputs), outputs
