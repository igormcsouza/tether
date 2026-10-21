"""Sub-agents and pipelines (Plane: orchestration). Each child/stage gets its own scripted route."""

from __future__ import annotations

import re
import sqlite3

from e2e.conftest import Tether
from e2e.proxy import session_id_in


def _sessions(t: Tether) -> list[sqlite3.Row]:
    c = sqlite3.connect(f"file:{t.ws / '.tether' / 'tether.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return list(c.execute("select * from sessions order by created_at"))


def test_agent_spawn_wait_read_and_query(tether: Tether, chaos) -> None:
    chaos.route("CHILD-TASK", ("done", "child says pineapple"))
    chaos.route(
        "PARENT-TASK",
        "agent spawn CHILD-TASK compute it",
        lambda body: f"agent wait {session_id_in(body)}",
        lambda body: f"agent read {session_id_in(body)} --full",
        lambda body: f"agent query {session_id_in(body)} pineapple",
        ("done", "parent finished"),
    )
    r = tether.run("PARENT-TASK", "--tools", "agent", "--max-steps", "8")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    child = next(s for s in _sessions(tether) if s["parent_id"] == r["id"])
    assert child["status"] == "COMPLETED" and child["result"] == "child says pineapple"
    outs = tether.tool_outputs(r["id"])
    assert re.match(r"ses_[0-9a-f]+", outs[0]), outs[
        0
    ]  # spawn returns the id at once (always async)
    assert "COMPLETED" in outs[1] and len(outs[1]) < 600, "wait returns a compact digest"
    assert outs[2].strip() == "child says pineapple"
    assert "pineapple" in outs[3]


def test_agent_send_resumes_a_finished_child(tether: Tether, chaos) -> None:
    chaos.route("CHILD-TASK", ("done", "first answer"), ("done", "second answer"))
    chaos.route(
        "PARENT-TASK",
        "agent spawn CHILD-TASK",
        lambda body: f"agent wait {session_id_in(body)}",
        lambda body: f"agent send {session_id_in(body)} now do more",
        lambda body: f"agent wait {session_id_in(body)}",
        lambda body: f"agent read {session_id_in(body)} --full",
        ("done", "ok"),
    )
    r = tether.run("PARENT-TASK", "--tools", "agent", "--max-steps", "10")
    assert r["status"] == "COMPLETED", r
    assert tether.tool_outputs(r["id"])[4].strip() == "second answer"


def test_child_sandbox_is_never_wider_than_the_parent(tether: Tether, chaos) -> None:
    chaos.route("CHILD-TASK", ("done", "ok"))
    chaos.route(
        "PARENT-TASK",
        "agent spawn CHILD-TASK",
        lambda b: f"agent wait {session_id_in(b)}",
        ("done", "ok"),
    )
    r = tether.run("PARENT-TASK", "--tools", "agent", "--sandbox", "read-only")
    assert r["status"] == "COMPLETED", r
    child = next(s for s in _sessions(tether) if s["parent_id"] == r["id"])
    assert '"profile": "read-only"' in child["sandbox_json"], child["sandbox_json"]


def test_pipeline_runs_stages_in_order_with_an_upstream_digest(tether: Tether, chaos) -> None:
    (tether.ws / "flow.yaml").write_text(
        "name: flow\nstages:\n"
        "  - id: draft\n    goal: 'STAGE-ONE: {{goal}}'\n"
        "  - id: review\n    goal: 'STAGE-TWO review the draft'\n    tools: edit\n"
    )
    chaos.route("STAGE-ONE", ("done", "the draft says kiwi"))
    chaos.route("STAGE-TWO", ("done", "reviewed"))
    p = tether.cli("pipeline", "--json", "--model", "e2e/scripted", "flow.yaml", "make a thing")
    assert p.returncode == 0, p.stderr
    rows = _sessions(tether)
    stages = [s for s in rows if s["parent_id"]]
    assert [s["status"] for s in stages] == ["COMPLETED", "COMPLETED"]
    second = next(b for b in chaos.requests if "STAGE-TWO" in str(b["messages"][1]))
    assert "kiwi" in str(second["messages"]), "stage 2 must see a digest of stage 1"
    assert [t["function"]["name"] for t in second["tools"]] == ["act"]
