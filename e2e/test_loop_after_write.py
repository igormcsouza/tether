"""A shell `for` loop runs through bash; a repeat after a write names the file and asks for
`done` (gap hunt, collect task: qwen3.5:9b re-read its finished file until a restart).

Scripted: replies are fixed, so the result never depends on the model.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_for_loop_and_loop_after_write(tether: Tether, chaos) -> None:
    (tether.ws / "a.py").write_text("x = 1\n")
    chaos.script(
        ('for f in *.py; do wc -l "$f"; done', None),
        ("edit write out.md", "| a.py | 1 |\n"),
        ("cat out.md", None),
        ("cat out.md", None),
        ("done", "wrote out.md"),
    )
    r = tether.run("count lines", "--tools", "bash,edit", "--max-steps", "8")
    assert r["rc"] == 0, r
    outputs = tether.tool_outputs(r["id"])
    assert "1 a.py" in outputs[0], outputs
    loop = next(o for o in outputs if o.startswith("[LOOP DETECTED]"))
    assert "You already wrote out.md" in loop and 'act("done"' in loop
