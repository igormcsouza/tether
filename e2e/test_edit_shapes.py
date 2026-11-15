"""#317: a correct diff sent to `edit replace <path>` is applied. Scripted: the proxy answers
with a fixed command, so the result never depends on what the model says."""

from __future__ import annotations

from e2e.conftest import Tether

DIFF = "@@ -1,3 +1,3 @@\n x = 1\n-y = 2\n+y = 20\n z = 3\n"


def test_diff_sent_to_replace_is_applied(tether: Tether, chaos) -> None:
    chaos.script(("edit replace f.py", DIFF))
    (tether.ws / "f.py").write_text("x = 1\ny = 2\nz = 3\n")
    tether.run("shapes", "--tools", "edit", "--verify", "true", "--max-steps", "3")
    assert (tether.ws / "f.py").read_text() == "x = 1\ny = 20\nz = 3\n"
