"""`tether replay`: re-run a recorded session and compare the two runs (scripted, no model)."""

from __future__ import annotations

import json
import sqlite3

from e2e.conftest import Tether


def _parent_of(tether: Tether, sid: str) -> str | None:
    c = sqlite3.connect(f"file:{tether.ws / '.tether' / 'tether.db'}?mode=ro", uri=True)
    try:
        row = c.execute("select parent_id from sessions where id=?", (sid,)).fetchone()
    finally:
        c.close()
    return row[0] if row else None


def test_replay_prints_a_comparison_of_both_runs(tether: Tether, chaos) -> None:
    chaos.script(("done", "first"))
    orig = tether.run("say first")
    chaos.requests.clear()
    chaos.script(("done", "second"))
    p = tether.cli("replay", orig["id"], "--model", f"e2e/{tether.model}")
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    assert lines[0].startswith(f"replay of {orig['id']} -> ses_"), lines[0]
    status = next(line for line in lines if line.startswith("status"))
    assert status.split()[1:] == ["COMPLETED", "COMPLETED"], status
    assert any(line.startswith("steps") for line in lines)
    assert any(line.startswith("tokens") for line in lines)


def test_replay_child_records_the_original_as_parent(tether: Tether, chaos) -> None:
    chaos.script(("done", "first"))
    orig = tether.run("say first")
    chaos.requests.clear()
    chaos.script(("done", "second"))
    p = tether.cli("replay", orig["id"], "--model", f"e2e/{tether.model}", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout.strip().splitlines()[-1])
    assert data["original"]["id"] == orig["id"]
    assert data["original"]["status"] == data["replay"]["status"] == "COMPLETED"
    child = data["replay"]["id"]
    assert child != orig["id"]
    assert _parent_of(tether, child) == orig["id"]
    assert _parent_of(tether, orig["id"]) is None
    assert tether.turns(child), "the replay records its own transcript"


def test_replay_of_an_unknown_id_exits_1(tether: Tether, chaos) -> None:
    chaos.script(("done", "ok"))
    tether.run("seed the store")
    p = tether.cli("replay", "ses_does_not_exist")
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
    assert "not found" in p.stderr
