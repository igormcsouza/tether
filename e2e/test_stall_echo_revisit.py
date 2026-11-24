"""After a passing test, bare `echo`s only talk: the stall guard ends the session before the step
cap (AD-50, bugfix-4). What tether sends and records (scripted, no model)."""

from __future__ import annotations

import json

from e2e.conftest import Tether

TEST = (
    "import unittest\nimport a\n\n\nclass T(unittest.TestCase):\n"
    "    def test_x(self):\n        self.assertEqual(a.X, 2)\n"
)
RUN = "bash -c 'python3 -m unittest test_t 2>&1'"


def test_bare_echoes_after_green_finish_by_the_harness(tether: Tether, chaos) -> None:
    (tether.ws / "test_t.py").write_text(TEST)
    chaos.script(
        ("edit write a.py", "X = 2\n"),
        RUN,
        ('echo "Done. The fix is complete."', None),
        ('echo "Submit."', None),
        ('echo "All green."', None),
        ('echo "Nothing left."', None),
        ('echo "Bye."', None),
        ("done", "never reached"),
    )  # fmt: skip
    d = tether.run("fix a.py so the test passes", "--tools", "edit,bash", "--max-steps", "20")
    assert (d["rc"], d["status"]) == (0, "COMPLETED"), d
    assert d["result"].startswith("Finished by the harness"), d["result"]
    events = tether.events(d["id"])
    assert len(events) <= 6 and events.count("loop_stall") == 4, events
    assert "[NUDGE] `echo` only prints back" in json.dumps(chaos.requests)
