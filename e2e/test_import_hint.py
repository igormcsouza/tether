"""AD-52: an import that cannot find a name gets one line saying where the name really is.

Scripted: the proxy plays the model, tether and python are real. go-counting shape: constants
were put inside the class, the tests import them from the module.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_a_name_inside_a_class_is_pointed_out(tether: Tether, chaos) -> None:
    (tether.ws / "go_counting.py").write_text("class Board:\n    WHITE = 'W'\n")
    chaos.script("bash python3 -c 'from go_counting import WHITE'", ("done", "ok"))
    r = tether.run("Make `from go_counting import WHITE` work", "--tools", "bash")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    out = tether.tool_outputs(r["id"])[0]
    assert "[hint] `WHITE` is defined inside `class Board` in go_counting.py" in out, out
