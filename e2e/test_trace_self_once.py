"""AD-24: after an edit the same tests still fail, so the auto-test carries a runtime trace, and a
method called again on the same object omits `self`.

Scripted: the proxy plays the model, tether, bash and python are real. connect shape: the board
repr on every method call filled the trace's char budget.
"""

from __future__ import annotations

from e2e.conftest import Tether

GAME = (
    "class G:\n    def __init__(self):\n        self.board = [[1, 2], [3, 4]]\n"
    "    def win(self):\n        return self.near(0) + self.near(1)\n"
    "    def near(self, r):\n        return r\n"
)
TEST = (
    "import unittest\nfrom g import G\n\n\nclass T(unittest.TestCase):\n"
    "    def test_it(self):\n        self.assertEqual(G().win(), 3)\n"
)


def test_the_trace_shows_the_same_self_once(tether: Tether, chaos) -> None:
    (tether.ws / "g.py").write_text(GAME)
    (tether.ws / "g_test.py").write_text(TEST)
    chaos.script(
        "bash python3 -m unittest discover -p '*_test.py'",
        "bash printf '# tried\\n' >> g.py",
        ("done", "ok"),
    )
    r = tether.run("Make the tests pass", "--tools", "bash", "--max-steps", "6")
    assert r["rc"] in (0, 2), r
    out = tether.tool_outputs(r["id"])[1]
    assert "[runtime trace of test_it" in out, out
    assert "win(self=G(board=" in out and "  near(r=0)" in out, out
    assert "near(self=" not in out, out
