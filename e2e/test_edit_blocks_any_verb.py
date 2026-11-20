"""`edit replace --lines`, `append` and `insert` apply SEARCH/REPLACE blocks, never write the
markers into the file (#332). Scripted: the proxy forces the edit calls."""

from __future__ import annotations

from typing import Any

import pytest

from e2e.conftest import Tether

BLOCK = "<<<<<<< SEARCH\nb\n=======\nB\n>>>>>>> REPLACE\n"


@pytest.mark.parametrize(
    "cmd", ["edit replace a.txt --lines 1:1", "edit append a.txt", "edit insert a.txt --line 1"]
)
def test_blocks_are_applied_by_every_verb(tether: Tether, chaos: Any, cmd: str) -> None:
    (tether.ws / "a.txt").write_text("a\nb\nc\n")
    chaos.script((cmd, BLOCK), ("done", "ok"))
    r = tether.run("replace b with B in a.txt", "--tools", "edit")
    assert r["rc"] == 0
    assert (tether.ws / "a.txt").read_text() == "a\nB\nc\n"
    assert "as replace" in tether.tool_outputs(r["id"])[0]
