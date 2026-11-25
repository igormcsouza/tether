"""Restart to the best version (AD-21): what tether sends and records (scripted, no model).

A version that fails 4 of 14 tests is the best so far (a near pass, at most 3 failing, is kept
in place instead). Three failing checks after edits restart the session, and the files go back
to that version, not to the starting stub.
"""

from __future__ import annotations

import json

from e2e.conftest import Tether
from e2e.proxy import Chaos

RUN = "bash -c 'python3 -m unittest test_t 2>&1'"
TESTS = "import unittest\nimport a\n\n\nclass T(unittest.TestCase):\n" + "".join(
    f"    def test_{n}(self):\n        self.assertEqual(a.v{n}, 1)\n" for n in range(14)
)


def _module(passing: set[int]) -> str:
    # the comment's length differs per version: same-size rewrites in one second would leave
    # Python's .pyc cache stale
    lines = [f"v{n} = {1 if n in passing else 0}\n" for n in range(14)]
    return "".join(lines) + f"# {'x' * (14 - len(passing))}\n"


def test_three_failing_checks_go_back_to_the_best_version(tether: Tether, chaos: Chaos) -> None:
    (tether.ws / "test_t.py").write_text(TESTS)
    stub = tether.ws / "a.py"
    stub.write_text(_module(set()))
    best = _module(set(range(10)))  # 4 of 14 fail: the best version so far
    chaos.script(
        RUN,  # the stub: red, untouched, so it does not count
        ("edit write a.py", best),  # auto-test: 4 fail (best recorded)
        ("edit write a.py", _module(set(range(6)))),  # 8 fail
        ("edit write a.py", _module({0, 1, 2})),  # 11 fail: the third failing check
        ("edit view a.py", None),  # the files are back to the best version
        ("done", "ok"),
    )  # fmt: skip
    d = tether.run("make the tests pass", "--tools", "edit,bash", "--max-steps", "20")
    turns = tether.turns(d["id"])
    restarts = [t for t in turns if t["event_type"] == "restart"]
    assert len(restarts) == 1, "one restart per session"
    body = restarts[0]["content"]
    assert body.startswith("[RESTART at step 4 from your best version.")
    assert "(it failed 4 tests)" in body and "test_10" in body
    viewed = tether.tool_outputs(d["id"])[-2]  # the view after the restart, before `done`
    assert "v9 = 1" in viewed and "v10 = 0" in viewed, "the best version, not the last try"
    assert (tether.ws / "a.py").read_text() == best
    assert "[RESTART at step 4" in json.dumps(chaos.requests[4]["messages"])
