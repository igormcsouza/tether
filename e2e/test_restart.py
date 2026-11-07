"""Restart after repeated failing check runs: what tether sends and records (scripted, no model)."""

from __future__ import annotations

import json
import os
import time

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
    chaos.script(  # after the first run, tether re-runs the tests after each edit ([auto-test])
        ("edit write a.py", "X = 1  # MARKER_FIRST\n"), RUN,
        ("edit write a.py", "X = 3\n"),
        ("edit write a.py", "X = 4  # LATEST\n"),
        ("edit write a.py", "X = 5\n"),
        ("done", "ok"),
    )  # fmt: skip
    d = tether.run("make the test pass", "--tools", "edit,bash", "--max-steps", "20")
    turns = tether.turns(d["id"])
    restarts = [t for t in turns if t["event_type"] == "restart"]
    assert len(restarts) == 1, "one restart per session"
    assert (
        "X = 4  # LATEST" in restarts[0]["content"] and "MARKER_FIRST" not in restarts[0]["content"]
    )
    after = json.dumps(chaos.requests[4]["messages"])
    assert "[RESTART at step 4" in after and "MARKER_FIRST" not in after
    assert "[auto-test]" in json.dumps(chaos.requests[3]["messages"]), "edits ran the tests"
    assert "MARKER_FIRST" in json.dumps(chaos.requests[3]["messages"]), "before it, full history"
    assert "MARKER_FIRST" in "".join(t["tool_stdin"] or "" for t in turns), "store keeps it all"


def test_a_near_pass_comes_back_in_place_and_the_history_stays(tether: Tether, chaos) -> None:
    tests = "".join(
        f"    def test_{n}(self):\n        self.assertEqual(a.{n.upper()}, 1)\n" for n in "uvwx"
    )
    (tether.ws / "test_t.py").write_text(
        f"import unittest\nimport a\n\n\nclass T(unittest.TestCase):\n{tests}"
    )
    stub = tether.ws / "a.py"  # a starting file: only those are put back
    stub.write_text("U = 0\n")
    os.utime(stub, (time.time() - 100,) * 2)
    best = "U = V = W = 1  # BEST\n"
    chaos.script(
        ("edit write a.py", best), RUN,
        ("edit write a.py", "U = V = 1\n"),
        ("edit write a.py", "U = 1  # WORST\n"),
        ("done", "ok"),
    )  # fmt: skip
    d = tether.run("make the tests pass", "--tools", "edit,bash", "--max-steps", "20")
    turns = tether.turns(d["id"])
    assert not [t for t in turns if t["event_type"] == "restart"]
    assert any("[RESTORED]" in t["content"] and "test_x" in t["content"] for t in turns)
    assert (tether.ws / "a.py").read_text() == best
    assert "# BEST" in json.dumps(chaos.requests[4]["messages"]), "history kept"
