"""`bash run.sh` runs the script through bash: what tether sends and records (no model)."""

from __future__ import annotations

from e2e.conftest import Tether


def test_bash_in_front_of_a_script_runs_it_without_exec_bit(tether: Tether, chaos) -> None:
    (tether.ws / "run.sh").write_text("echo SCRIPT_MARKER_OK\n")  # no exec bit
    chaos.script("bash run.sh", ("done", "ok"))
    r = tether.run("run the script", "--tools", "bash")
    assert "SCRIPT_MARKER_OK" in tether.tool_outputs(r["id"])[0]
    assert tether.events(r["id"])[0] == "ok"
