"""F5: a bash command that breaks a Python file is undone and the model is told.

Scripted: the replies are fixed, so the result never depends on what the model answers.
"""

from __future__ import annotations

from e2e.conftest import Tether

GOOD = "def f(x):\n    return x + 1\n"


def test_a_bash_write_that_breaks_python_is_undone(tether: Tether, chaos) -> None:
    # the first command leaves m.py unparsable (a printf escape gone wrong); the harness must put
    # the old bytes back before the model's next step
    chaos.script(
        ("printf 'def f(x):\\n    return x +\\n' > m.py", None),
        ("ls", None),
    )
    (tether.ws / "m.py").write_text(GOOD)
    tether.run("broken", "--tools", "bash", "--max-steps", "2")
    assert (tether.ws / "m.py").read_text() == GOOD


def test_a_sed_i_that_breaks_python_is_undone(tether: Tether, chaos) -> None:
    # sed -i is not a redirect: the file is found because the command names it
    chaos.script(("sed -i 's/return x/return (x/' m.py", None), ("ls", None))
    (tether.ws / "m.py").write_text(GOOD)
    tether.run("broken", "--tools", "bash", "--max-steps", "2")
    assert (tether.ws / "m.py").read_text() == GOOD
