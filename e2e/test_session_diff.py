"""`tether diff <id>`: file changes of a session. Scripted: the proxy plays the model."""

from __future__ import annotations

from e2e.conftest import Tether


def _edit_and_add(tether: Tether, chaos) -> dict:
    (tether.ws / "app.txt").write_text("old\n")
    chaos.script(
        ("edit replace app.txt", "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"),
        ("edit write added.txt", "hi\n"),
        ("done", "ok"),
    )
    r = tether.run("change", "--tools", "edit")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    return r


def test_diff_shows_edit_as_minus_plus_and_new_file_as_added(tether: Tether, chaos) -> None:
    r = _edit_and_add(tether, chaos)
    p = tether.cli("diff", r["id"])
    assert p.returncode == 0, p.stderr
    assert "-old" in p.stdout and "+new" in p.stdout
    assert "added.txt" in p.stdout and "+hi" in p.stdout


def test_diff_stat_lists_each_changed_file(tether: Tether, chaos) -> None:
    r = _edit_and_add(tether, chaos)
    p = tether.cli("diff", "--stat", r["id"])
    assert p.returncode == 0, p.stderr
    assert "app.txt" in p.stdout and "added.txt" in p.stdout


def test_diff_unknown_session_exits_1(tether: Tether, chaos) -> None:
    _edit_and_add(tether, chaos)
    p = tether.cli("diff", "ses_doesnotexist")
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
