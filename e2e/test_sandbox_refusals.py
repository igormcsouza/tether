"""Sandbox refusals are actionable (#124 item 3). Scripted: the proxy forces the refused action,
so the result never depends on the model; tether alone must say no and say what to do instead."""

from __future__ import annotations

from e2e.conftest import Tether

_ELEVATE = "su" + "do ls"


def test_bash_refusal_names_rule_and_alternative(tether: Tether, chaos) -> None:
    chaos.script(f"bash {_ELEVATE}", ("done", "ok"))
    r = tether.run("elevate", "--tools", "bash")
    out = tether.tool_outputs(r["id"])[0]
    assert "Sandbox violation:" in out and "Instead:" in out, out


def test_edit_refusal_outside_workspace_is_actionable(tether: Tether, chaos) -> None:
    chaos.script(("edit write ../escape.txt", "pwned"), ("done", "ok"))
    r = tether.run("escape", "--tools", "edit")
    out = tether.tool_outputs(r["id"])[0]
    assert "Instead:" in out and "inside the workspace" in out, out
    assert not (tether.ws.parent / "escape.txt").exists()


def test_edit_refusal_protected_path_is_actionable(tether: Tether, chaos) -> None:
    chaos.script(("edit write .env", "KEY=1"), ("done", "ok"))
    r = tether.run("secret", "--tools", "edit")
    out = tether.tool_outputs(r["id"])[0]
    assert "protected" in out and "not writable" in out and "Instead:" in out, out
    assert not (tether.ws / ".env").exists()
