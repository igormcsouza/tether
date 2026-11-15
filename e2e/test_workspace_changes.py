"""H2: a change is found by looking at the workspace, not at the command text. Scripted replies,
no model: `perl -pi` has no parsing rule, yet `tether diff` must show its edit."""

from __future__ import annotations

from e2e.conftest import Tether


def test_a_perl_edit_shows_in_tether_diff(tether: Tether, chaos) -> None:
    (tether.ws / "f.txt").write_text("old\n")
    chaos.script(("bash", "perl -pi -e 's/old/new/' f.txt"), ("done", "ok"))
    r = tether.run("perl edit", "--tools", "bash")
    assert (tether.ws / "f.txt").read_text() == "new\n"
    p = tether.cli("diff", r["id"])
    assert p.returncode == 0, p.stderr
    assert "-old" in p.stdout and "+new" in p.stdout
    assert "could not track" not in p.stdout
