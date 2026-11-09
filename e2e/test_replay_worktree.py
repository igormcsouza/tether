"""`tether replay --worktree`: the replay runs on its own branch and the caller's checkout stays
clean. Scripted: the proxy plays the model, while tether and git are real."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

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


def _sandbox_config(tether: Tether, sid: str) -> dict[str, object]:
    c = sqlite3.connect(f"file:{tether.ws / '.tether' / 'tether.db'}?mode=ro", uri=True)
    try:
        row = c.execute("select sandbox_json from sessions where id=?", (sid,)).fetchone()
    finally:
        c.close()
    assert row is not None, sid
    return json.loads(row[0])


def test_replay_worktree_leaves_the_checkout_alone(tether: Tether, chaos) -> None:
    env = tether.env | GIT_ID
    (tether.ws / "calc.py").write_text("x = 1\n")
    _git(tether.ws, env, "init", "-q")
    _git(tether.ws, env, "add", "-A")
    _git(tether.ws, env, "commit", "-qm", "base")

    chaos.script(("done", "first"))
    orig = tether.run("say first")
    chaos.requests.clear()
    chaos.script(("done", "second"))
    p = tether.cli("replay", orig["id"], "--worktree", "--model", f"e2e/{tether.model}", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout.strip().splitlines()[-1])
    child = data["replay"]["id"]

    cfg = _sandbox_config(tether, child)
    worktree = Path(str(cfg["worktree"]))
    assert worktree.is_dir()
    assert worktree.resolve() != tether.ws.resolve()
    assert cfg["branch"] == f"tether/{child}"
    assert (tether.ws / "calc.py").read_text() == "x = 1\n"
    status = _git(tether.ws, env, "status", "--porcelain").splitlines()
    dirty = [ln for ln in status if ".tether/" not in ln]
    assert dirty == [], dirty
