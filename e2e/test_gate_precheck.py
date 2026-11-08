"""Gate pre-check (#82): a verify gate whose program is missing is refused before any model call.

Scripted: the proxy plays the model, tether is real.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_missing_gate_program_is_refused_before_any_model_call(tether: Tether, chaos) -> None:
    chaos.script(("done", "x"))
    r = tether.run("gate", "--verify", "no-such-tool-xyz")
    assert (r["rc"], r["status"]) == (3, "FAILED")
    assert r["failure"]["kind"] == "gate" and "misconfigured" in str(r["failure"])
    assert "no-such-tool-xyz" in str(r["failure"])
    assert chaos.requests == [], "a misconfigured gate must not reach the model"


def test_good_gate_program_lets_scripted_done_complete(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    r = tether.run("gate", "--verify", "python3 -c 'print(1)'")
    assert (r["rc"], r["status"], r["result"]) == (0, "COMPLETED", "ok")
    assert chaos.requests, "a runnable gate lets the model run normally"
