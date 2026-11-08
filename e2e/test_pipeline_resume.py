"""`tether pipeline --resume`: a failed stage is retried; completed stages never re-run."""

from __future__ import annotations

import sqlite3

from e2e.conftest import Tether


def _sessions(t: Tether) -> list[sqlite3.Row]:
    c = sqlite3.connect(f"file:{t.ws / '.tether' / 'tether.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return list(c.execute("select * from sessions order by created_at"))


def _write_flow(t: Tether) -> None:
    # stage 2 has a gate that passes only once flag.txt exists, so the first run fails there
    (t.ws / "flow.yaml").write_text(
        "name: flow\nstages:\n"
        "  - id: draft\n    goal: 'STAGE-ONE: {{goal}}'\n"
        "  - id: review\n    goal: 'STAGE-TWO review the draft'\n"
        "    verify: test -f flag.txt\n"
    )


def test_resume_reruns_only_the_failed_stage(tether: Tether, chaos) -> None:
    _write_flow(tether)
    chaos.route("STAGE-ONE", ("done", "the draft says kiwi"))
    chaos.route("STAGE-TWO", *[("done", "x")] * 10)
    p = tether.cli("pipeline", "--json", "--model", "e2e/scripted", "flow.yaml", "make a thing")
    assert p.returncode != 0, p.stderr
    root = next(s for s in _sessions(tether) if not s["parent_id"])
    assert root["status"] == "FAILED", root["status"]

    (tether.ws / "flag.txt").write_text("ok")
    p2 = tether.cli("pipeline", "--json", "--resume", root["id"])
    assert p2.returncode == 0, p2.stderr

    rows = _sessions(tether)
    assert next(s for s in rows if s["id"] == root["id"])["status"] == "COMPLETED"
    children = [s for s in rows if s["parent_id"] == root["id"]]
    # first run: stage one, then stage two (failed). resume: stage two only, so stage one
    # has exactly one child session
    assert children[0]["status"] == "COMPLETED"
    assert "STAGE-ONE" in children[0]["goal"], children[0]["goal"]
    assert [s["goal"] for s in children].count(children[0]["goal"]) == 1
    assert children[-1]["status"] == "COMPLETED"
    assert "STAGE-TWO" in children[-1]["goal"], children[-1]["goal"]


def test_resume_of_an_unknown_id_exits_1(tether: Tether) -> None:
    p = tether.cli("pipeline", "--resume", "ses_doesnotexist")
    assert p.returncode == 1, p.stderr
    assert "not found" in p.stderr, p.stderr
