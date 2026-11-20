"""SEARCH/REPLACE blocks in stdin are applied, never written as text, by every verb (#332)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import Harness, SandboxPolicy

BLOCK = "<<<<<<< SEARCH\nb\n=======\nB\n>>>>>>> REPLACE\n"
NOTE = "(applied as replace: SEARCH/REPLACE blocks on an existing file)"
VERBS = [
    "edit replace f.txt --lines 1:1",
    "edit append f.txt",
    "edit insert f.txt --line 1",
    "edit write f.txt",
]


def _mux(tmp_path: Path):  # type: ignore[no-untyped-def]
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit"], sandbox=sandbox)
    return harness.build_multiplexer("ses_blocks", ["edit"], sandbox, "ollama/qwen3.5:9b")


@pytest.mark.parametrize("cmd", VERBS)
async def test_blocks_are_applied_on_an_existing_file(tmp_path: Path, cmd: str) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    out = (await _mux(tmp_path).execute(cmd, stdin=BLOCK)).output
    assert (tmp_path / "f.txt").read_text() == "a\nB\nc\n"
    assert NOTE in out


@pytest.mark.parametrize("cmd", VERBS)
async def test_a_block_that_does_not_match_changes_nothing(tmp_path: Path, cmd: str) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    bad = BLOCK.replace("SEARCH\nb\n", "SEARCH\nzzz\n")
    out = (await _mux(tmp_path).execute(cmd, stdin=bad)).output
    assert out.startswith("Error: ")
    assert "nothing changed" in out
    assert (tmp_path / "f.txt").read_text() == "a\nb\nc\n"


async def test_plain_text_keeps_each_verb_as_it_was(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    mux = _mux(tmp_path)
    await mux.execute("edit replace f.txt --lines 2:2", stdin="B\n")
    await mux.execute("edit append f.txt", stdin="d\n")
    await mux.execute("edit insert f.txt --line 1", stdin="0\n")
    assert (tmp_path / "f.txt").read_text() == "0\na\nB\nc\nd\n"


async def test_a_new_file_may_hold_markers_as_text(tmp_path: Path) -> None:
    out = (await _mux(tmp_path).execute("edit write new.txt", stdin=BLOCK)).output
    assert out.startswith("Wrote ")
    assert (tmp_path / "new.txt").read_text() == BLOCK
