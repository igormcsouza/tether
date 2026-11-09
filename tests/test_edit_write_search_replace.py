"""`edit write` with SEARCH/REPLACE blocks on an existing file acts as `edit replace` (#267)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tether import Harness, SandboxPolicy


def _mux(tmp_path: Path) -> Any:
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit"], sandbox=sandbox)
    return harness.build_multiplexer("ses_e", ["edit"], sandbox, "ollama/qwen3.5:9b")


async def test_write_with_block_acts_as_replace(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\nc\n")
    block = "<<<<<<< SEARCH\nb\n=======\nB\n>>>>>>> REPLACE\n"
    await _mux(tmp_path).execute("edit write a.txt", stdin=block)
    assert (tmp_path / "a.txt").read_text() == "a\nB\nc\n"


async def test_multiple_blocks(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\nc\n")
    stdin = (
        "<<<<<<< SEARCH\na\n=======\nA\n>>>>>>> REPLACE\n"
        "<<<<<<< SEARCH\nc\n=======\nC\n>>>>>>> REPLACE\n"
    )
    await _mux(tmp_path).execute("edit write a.txt", stdin=stdin)
    assert (tmp_path / "a.txt").read_text() == "A\nb\nC\n"


async def test_missing_search_leaves_file_unchanged(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    block = "<<<<<<< SEARCH\nzzz\n=======\nY\n>>>>>>> REPLACE\n"
    (tmp_path / "a.txt").write_text("a\nb\n")
    replace_out = (await mux.execute("edit replace a.txt", stdin=block)).output
    assert (tmp_path / "a.txt").read_text() == "a\nb\n"

    (tmp_path / "a.txt").write_text("a\nb\n")
    write_out = (await mux.execute("edit write a.txt", stdin=block)).output
    assert (tmp_path / "a.txt").read_text() == "a\nb\n"
    assert write_out == replace_out


async def test_new_file_with_markers_is_written(tmp_path: Path) -> None:
    block = "<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n"
    await _mux(tmp_path).execute("edit write new.txt", stdin=block)
    assert (tmp_path / "new.txt").read_text() == block


async def test_incomplete_block_is_plain_write(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\n")
    stdin = "<<<<<<< SEARCH\nb\n"
    await _mux(tmp_path).execute("edit write a.txt", stdin=stdin)
    assert (tmp_path / "a.txt").read_text() == stdin


async def test_search_without_closing_marker_is_plain_write(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\n")
    stdin = "<<<<<<< SEARCH\nb\n=======\nB\n"
    await _mux(tmp_path).execute("edit write a.txt", stdin=stdin)
    assert (tmp_path / "a.txt").read_text() == stdin


async def test_search_without_divider_is_plain_write(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\n")
    stdin = "<<<<<<< SEARCH\nb\n>>>>>>> REPLACE\n"
    await _mux(tmp_path).execute("edit write a.txt", stdin=stdin)
    assert (tmp_path / "a.txt").read_text() == stdin


async def test_ambiguous_count_is_plain_write(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\n")
    stdin = "<<<<<<< SEARCH\na\n=======\nA\n>>>>>>> REPLACE\n<<<<<<< SEARCH\nb\n"
    await _mux(tmp_path).execute("edit write a.txt", stdin=stdin)
    assert (tmp_path / "a.txt").read_text() == stdin


async def test_message_mentions_replace(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\nc\n")
    block = "<<<<<<< SEARCH\nb\n=======\nB\n>>>>>>> REPLACE\n"
    out = (await _mux(tmp_path).execute("edit write a.txt", stdin=block)).output
    assert out == (
        "Replaced 1 block(s) in `a.txt`."
        " (applied as replace: SEARCH/REPLACE blocks on an existing file)"
    )
    assert "\n" not in out


# Empty REPLACE deletes only the SEARCH text; an empty SEARCH must not crash (#267).
async def test_write_with_empty_replace_deletes_only_search_text(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a\nb\nc\n")
    block = "<<<<<<< SEARCH\nb\n=======\n>>>>>>> REPLACE\n"
    out = (await _mux(tmp_path).execute("edit write a.txt", stdin=block)).output
    assert (tmp_path / "a.txt").read_text() == "a\n\nc\n"
    assert out.endswith("(applied as replace: SEARCH/REPLACE blocks on an existing file)")


async def test_empty_search_is_error_and_file_unchanged(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    block = "<<<<<<< SEARCH\n\n=======\nX\n>>>>>>> REPLACE\n"
    (tmp_path / "a.txt").write_text("a\nb\n")
    for cmd in ("edit write a.txt", "edit replace a.txt"):
        out = (await mux.execute(cmd, stdin=block)).output
        assert out.startswith("Error: SEARCH block 1 is empty; nothing changed.")
        assert (tmp_path / "a.txt").read_text() == "a\nb\n"
