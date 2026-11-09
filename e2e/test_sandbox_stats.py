"""A sandbox refusal is counted as a `sandbox_violation` event (#124 item 8). Scripted: the proxy
forces the refused action, so the result never depends on the model."""

from __future__ import annotations

from e2e.conftest import Tether

_ELEVATE = "su" + "do ls"


def test_bash_refusal_is_a_sandbox_violation_event(tether: Tether, chaos) -> None:
    chaos.script(f"bash {_ELEVATE}", ("done", "ok"))
    r = tether.run("elevate", "--tools", "bash")
    assert "sandbox_violation" in tether.events(r["id"]), tether.events(r["id"])
