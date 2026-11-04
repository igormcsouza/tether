"""Restart after repeated failing check runs: what tether sends and records (scripted, no model)."""

from __future__ import annotations

import json

from e2e.conftest import Tether

TEST = (
    "import unittest\nimport a\n\n\nclass T(unittest.TestCase):\n"
    "    def test_x(self):\n        self.assertEqual(a.X, 2)\n"
)
RUN = "bash -c 'python3 -m unittest test_t 2>&1'"


def test_third_failing_check_restarts_with_a_description_not_a_replay(
    tether: Tether, chaos
) -> None:
    (tether.ws / "test_t.py").write_text(TEST)
    chaos.script(
        ("edit write a.py", "X = 1  # MARKER_FIRST\n"), RUN,
        ("edit write a.py", "X = 3\n"), RUN,
        ("edit write a.py", "X = 4  # LATEST\n"), RUN,
        ("edit write a.py", "X = 5\n"), RUN,
        ("done", "ok"),
    )  # fmt: skip
    d = tether.run("make the test pass", "--tools", "edit,bash", "--max-steps", "20")
    turns = tether.turns(d["id"])
    restarts = [t for t in turns if t["event_type"] == "restart"]
    assert len(restarts) == 1, "one restart per session"
    assert (
        "X = 4  # LATEST" in restarts[0]["content"] and "MARKER_FIRST" not in restarts[0]["content"]
    )
    after = json.dumps(chaos.requests[6]["messages"])
    assert "[RESTART at step" in after and "MARKER_FIRST" not in after
    assert "MARKER_FIRST" in json.dumps(chaos.requests[5]["messages"]), "before it, full history"
    assert "MARKER_FIRST" in "".join(t["tool_stdin"] or "" for t in turns), "store keeps it all"
