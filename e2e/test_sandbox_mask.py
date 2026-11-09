"""S8 (#124 item 1): in a masked git workspace, `git status` and `cat .env` succeed under the
real CLI and the secret never reaches what tether recorded. Scripted: no model involved."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from e2e.conftest import Tether

# `_run_argv` appends `[exit N]` (or `[exit N: no output]`) for nonzero exits.
_NONZERO_EXIT = re.compile(r"\[exit [1-9]\d*")


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bwrap")
def test_git_and_cat_work_in_masked_workspace(tether: Tether, chaos) -> None:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], cwd=tether.ws, check=True)
    (tether.ws / "notes.txt").write_text("TODO\n")
    subprocess.run([*git, "add", "notes.txt"], cwd=tether.ws, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=tether.ws, check=True)
    (tether.ws / ".env").write_text("TOKEN=hunter2")
    (tether.ws / "new.txt").write_text("untracked\n")
    chaos.script("bash git status --short", "bash cat .env", ("done", "ok"))
    r = tether.run("inspect the repo", "--tools", "bash")
    assert r["rc"] == 0, r
    outs = tether.tool_outputs(r["id"])[:2]
    assert len(outs) == 2, outs
    assert "?? new.txt" in outs[0], outs[0]
    for out in outs:
        assert "hunter2" not in out, out
        assert "Sandbox violation" not in out, out
        assert not out.startswith("Error"), out
        assert "Permission denied" not in out and "unable to access" not in out, out
        assert not _NONZERO_EXIT.search(out), out
    assert all("hunter2" not in str(t["content"]) for t in tether.turns(r["id"]))
