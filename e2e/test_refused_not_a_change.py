"""#318: a refused command is not a change. Scripted: the proxy forces refused edits (no stdin),
so the result never depends on the model; the session must end WAITING_INPUT, not COMPLETED."""

from __future__ import annotations

from e2e.conftest import Tether


def test_refused_edits_do_not_finish_as_completed(tether: Tether, chaos) -> None:
    # 12 refused edits outlast the 10 steps: the stall guard must not finish on the green gate
    chaos.script(*[("edit replace f.py --lines 1:1", None)] * 12)
    (tether.ws / "f.py").write_text("x = 1\n")
    r = tether.run("refused", "--tools", "edit", "--verify", "true", "--max-steps", "10")
    assert (tether.ws / "f.py").read_text() == "x = 1\n"
    assert (r["rc"], r["status"]) == (2, "WAITING_INPUT"), r
    assert "Finished by the harness" not in (r["result"] or ""), r
