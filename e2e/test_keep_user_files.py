"""#350: files that were in the workspace before the session come back after a command deletes
them, unless the goal asks to delete things.

Scripted: the proxy plays the model, tether and bash are real. Coding Ladder shell-5 shape: the
model deletes data/ to try the script's "data/ is missing" branch.
"""

from __future__ import annotations

from e2e.conftest import Tether


def _data(tether: Tether) -> None:
    (tether.ws / "data").mkdir()
    (tether.ws / "data" / "todo list.txt").write_text("milk\n")
    (tether.ws / "data" / "budget.csv").write_text("a,1\n")


def test_deleted_user_files_come_back_and_the_command_saw_them_gone(tether: Tether, chaos) -> None:
    _data(tether)
    chaos.script("bash rm -rf data && ls data || echo gone", ("done", "ok"))
    r = tether.run("Fix backup.sh so it fails loudly when data/ is missing", "--tools", "bash")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    out = tether.tool_outputs(r["id"])[0]
    assert "gone" in out and "[KEPT] `data/budget.csv`, `data/todo list.txt`" in out, out
    assert (tether.ws / "data" / "todo list.txt").read_text() == "milk\n"


def test_a_goal_that_asks_to_delete_keeps_the_deletion(tether: Tether, chaos) -> None:
    _data(tether)
    chaos.script("bash rm -rf data", ("done", "ok"))
    r = tether.run("Delete the data folder", "--tools", "bash")
    assert r["rc"] == 0, r
    assert not (tether.ws / "data").exists()
    assert "[KEPT]" not in "".join(tether.tool_outputs(r["id"]))
