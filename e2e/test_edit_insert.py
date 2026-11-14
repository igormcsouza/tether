"""#320: `edit insert` adds lines without replacing the kept line. Scripted: the proxy forces the
edit calls, so the result never depends on what the model answers."""

from __future__ import annotations

from e2e.conftest import Tether


def test_scripted_insert_keeps_every_line(tether: Tether, chaos) -> None:
    # one insert before line 2, then the run ends at the step limit
    chaos.script(("edit insert f.txt --line 2", "X\n"), *[("edit view f.txt", None)] * 12)
    (tether.ws / "f.txt").write_text("a\nb\nc\n")
    tether.run("insert", "--tools", "edit", "--verify", "true", "--max-steps", "10")
    assert (tether.ws / "f.txt").read_text() == "a\nX\nb\nc\n"
