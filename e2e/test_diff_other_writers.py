"""`tether diff` sees writes by sed -i / mv / python, and names untracked ones (#280). Scripted."""

from __future__ import annotations

import os
import time

from e2e.conftest import Tether


def _pre_date(tether: Tether, *names: str) -> None:
    past = time.time() - 3600
    for name in names:
        os.utime(tether.ws / name, (past, past))


def test_sed_mv_and_untracked_python_are_all_visible(tether: Tether, chaos) -> None:
    (tether.ws / "f").write_text("a\n")
    (tether.ws / "g").write_text("old\n")
    (tether.ws / "new").write_text("new\n")
    (tether.ws / "w.py").write_text("open('out.txt', 'w').write('1')\n")
    _pre_date(tether, "f", "g", "new", "w.py")
    chaos.script(
        "bash sed -i 's/a/b/' f",
        "bash mv new g",
        "bash python3 w.py",
        ("done", "ok"),
    )
    r = tether.run("change files", "--tools", "bash")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    p = tether.cli("diff", r["id"])
    assert p.returncode == 0, p.stderr
    assert "-a\n" in p.stdout and "+b\n" in p.stdout, p.stdout
    assert "-old\n" in p.stdout and "+new\n" in p.stdout, p.stdout
    assert "could not track: out.txt" in p.stdout, p.stdout
    assert "no file changes" not in p.stdout
    s = tether.cli("diff", "--stat", r["id"])
    assert s.returncode == 0 and "could not track: out.txt" in s.stdout, s.stdout


def test_read_only_session_still_says_no_file_changes(tether: Tether, chaos) -> None:
    (tether.ws / "f").write_text("a\n")
    _pre_date(tether, "f")
    chaos.script("bash cat f", ("done", "ok"))
    r = tether.run("read", "--tools", "bash")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    p = tether.cli("diff", r["id"])
    assert p.returncode == 0 and "no file changes recorded" in p.stdout, p.stdout
