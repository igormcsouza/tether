"""AD-24 (F5): a bash write that leaves a .py file unparsable is undone, and the note quotes the
line the parser stopped at.

Scripted: the proxy plays the model, tether and bash are real. forth shape: `raise` inside a
lambda, which qwen retyped 12 times when the note named only the error.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_the_revert_note_quotes_the_broken_line(tether: Tether, chaos) -> None:
    (tether.ws / "forth.py").write_text("def evaluate(x):\n    pass\n")
    chaos.script(
        "bash printf 'f = lambda b: 1 if b else (raise ValueError())\\n' > forth.py",
        ("done", "ok"),
    )
    r = tether.run("Implement forth.py", "--tools", "bash")
    assert r["rc"] == 0, r
    out = tether.tool_outputs(r["id"])[0]
    assert "[REVERTED] `forth.py`" in out, out
    assert "line 1: `f = lambda b: 1 if b else (raise ValueError())`" in out, out
    assert (tether.ws / "forth.py").read_text() == "def evaluate(x):\n    pass\n"
