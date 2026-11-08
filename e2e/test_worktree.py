"""`tether run --worktree`: the session works on its own branch and the caller's checkout stays
clean. Scripted: the proxy plays the model, while tether and git are real."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from e2e.conftest import Tether

GIT_ID = {
    "GIT_AUTHOR_NAME": "e2e",
    "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
    "GIT_COMMITTER_NAME": "e2e",
    "GIT_COMMITTER_EMAIL": "e2e@example.invalid",
}


def _git(cwd: Path, env: dict[str, str], *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _init_repo(tether: Tether) -> None:
    env = tether.env | GIT_ID
    (tether.ws / "README.md").write_text("base\n")
    _git(tether.ws, env, "init", "-q")
    _git(tether.ws, env, "add", "README.md")
    _git(tether.ws, env, "commit", "-q", "-m", "init")


def _status(tether: Tether, sid: str) -> dict[str, Any]:
    out = tether.cli("status", sid, "--json").stdout.strip().splitlines()
    return json.loads(out[-1])


def test_worktree_run_commits_to_tether_branch_and_leaves_checkout_clean(
    tether: Tether, chaos
) -> None:
    _init_repo(tether)
    chaos.script(("edit write out.txt", "from the worktree"), ("done", "ok"))
    r = tether.run("write a file", "--worktree", "--tools", "edit")
    assert r["rc"] == 0, r["stderr"]
    sid = r["id"]
    st = _status(tether, sid)
    assert st["branch"] == f"tether/{sid}" and st["commit"] is not None, st
    shown = _git(tether.ws, tether.env, "show", f"tether/{sid}:out.txt")
    assert shown.strip() == "from the worktree"
    assert not (tether.ws / "out.txt").exists(), "the caller's checkout must stay clean"


def test_worktree_outside_a_git_repo_exits_1(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    r = tether.run("no repo", "--worktree", "--tools", "edit")
    assert r["rc"] == 1, r
    assert "needs a git repository" in str(r)
