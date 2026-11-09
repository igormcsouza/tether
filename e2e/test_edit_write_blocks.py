"""`edit write` with SEARCH/REPLACE blocks on an existing file acts as `edit replace` (#267)."""

from __future__ import annotations

from typing import Any

from e2e.conftest import Tether


def test_write_with_block_is_applied_as_replace(tether: Tether, chaos: Any) -> None:
    (tether.ws / "a.txt").write_text("a\nb\nc\n")
    block = "<<<<<<< SEARCH\nb\n=======\nB\n>>>>>>> REPLACE\n"
    chaos.script(("edit write a.txt", block), ("done", "ok"))
    r = tether.run("replace b with B in a.txt", "--tools", "edit")
    assert r["rc"] == 0
    assert (tether.ws / "a.txt").read_text() == "a\nB\nc\n"
    assert "as replace" in tether.tool_outputs(r["id"])[0]
