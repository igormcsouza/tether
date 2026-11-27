"""A missing package gets a workspace-venv hint once (AD-54); under any kernel jail a read
outside the workspace is not refused by text rules (AD-35).

Scripted: replies are fixed, so the result never depends on the model.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_missing_package_hint_once_and_host_reads(tether: Tether, chaos) -> None:
    missing = "python3 -c 'import no_such_pkg_e2e'"
    chaos.script((missing, None), (missing + " ", None), ("ls /usr/bin", None), ("done", "ok"))
    r = tether.run("use a package", "--tools", "bash", "--max-steps", "6")
    assert r["rc"] == 0, r
    outputs = tether.tool_outputs(r["id"])
    assert "[hint] `no_such_pkg_e2e` is not installed" in outputs[0], outputs
    assert "[hint]" not in outputs[1]  # once per package
    assert "Sandbox violation" not in outputs[2] and "python3" in outputs[2]
