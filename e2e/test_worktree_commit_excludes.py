"""`run --worktree`: a scripted run leaves bytecode and caches out of the branch commit.
Scripted: the proxy plays the model, tether is real."""

from __future__ import annotations

import subprocess
from pathlib import Path

from e2e.conftest import Tether

SCRIPT = (
    "bash mkdir -p __pycache__ .pytest_cache && echo 'print(1)' > calc.py && "
    "echo b > __pycache__/calc.cpython-312.pyc && echo c > .pytest_cache/x"
)


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout


def test_worktree_commit_skips_bytecode_and_caches(tether: Tether, chaos) -> None:
    _git(tether.ws, "init", "-q")
    _git(
        tether.ws,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    chaos.script(SCRIPT, ("done", "ok"))
    r = tether.run("add calc", "--tools", "bash", "--worktree")
    assert r.get("commit") is not None, r
    shown = _git(Path(r["worktree"]), "show", "--name-only", "--format=", "HEAD")
    assert set(shown.split()) == {"calc.py"}
