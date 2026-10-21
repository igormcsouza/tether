"""Overwrite summary of `edit write` (#40) and the `edit` help budget."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy
from tether.context import estimate_tokens


def _mux(tmp_path: Path):  # type: ignore[no-untyped-def]
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit"], sandbox=sandbox)
    return harness.build_multiplexer("ses_e", ["edit"], sandbox, "ollama/qwen3.5:9b")


async def test_new_file_message_unchanged(tmp_path: Path) -> None:
    out = (await _mux(tmp_path).execute("edit write a.txt", stdin="a\nb\n")).output
    assert out == "Wrote 4 chars (2 lines) to `a.txt`."


async def test_overwrite_one_line_changed(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    await mux.execute("edit write a.txt", stdin="a\nb\nc\n")
    out = (await mux.execute("edit write a.txt", stdin="a\nX\nc\n")).output
    assert out == "Replaced 3 lines with 3 (1 removed, 1 added; first removed: b)"


async def test_overwrite_shrink_points_to_replace(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    await mux.execute("edit write a.txt", stdin="".join(f"line{i}\n" for i in range(10)))
    out = (await mux.execute("edit write a.txt", stdin="line0\nline1\n")).output
    assert "Replaced 10 lines with 2 (8 removed, 0 added; first removed: line2)" in out
    assert "edit replace <path> --lines a:b" in out


async def test_overwrite_growth_has_no_pointer(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    await mux.execute("edit write a.txt", stdin="a\n")
    out = (await mux.execute("edit write a.txt", stdin="a\nb\nc\n")).output
    assert out == "Replaced 1 line with 3 (0 removed, 2 added; first removed: none)"


async def test_identical_overwrite(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    await mux.execute("edit write a.txt", stdin="a\nb\n")
    out = (await mux.execute("edit write a.txt", stdin="a\nb\n")).output
    assert "(0 removed, 0 added; first removed: none)" in out


async def test_first_removed_truncated(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    await mux.execute("edit write a.txt", stdin="  " + "x" * 100 + "\n")
    out = (await mux.execute("edit write a.txt", stdin="y\n")).output
    assert f"first removed: {'x' * 60})" in out


async def test_edit_help_within_budget(tmp_path: Path) -> None:
    help_text = (await _mux(tmp_path).execute("edit --help")).output
    assert estimate_tokens(help_text) <= 60


async def test_overwrite_empty_old_file(tmp_path: Path) -> None:
    (tmp_path / "e.txt").write_text("")
    out = (await _mux(tmp_path).execute("edit write e.txt", stdin="a\n")).output
    assert out == "Replaced 0 lines with 1 (0 removed, 1 added; first removed: none)"


async def test_trailing_newline_only_change(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    await mux.execute("edit write a.txt", stdin="a\nb\n")
    out = (await mux.execute("edit write a.txt", stdin="a\nb")).output
    assert "only whitespace/newline changes" in out
    assert "0 removed" not in out


async def test_overwrite_non_utf8_old_content(tmp_path: Path) -> None:
    (tmp_path / "b.bin").write_bytes(b"ok\n\xff\xfe\n")
    out = (await _mux(tmp_path).execute("edit write b.bin", stdin="ok\n")).output
    assert out.startswith("Replaced 2 lines with 1 (1 removed, 0 added;")
    assert "File shrank" in out


async def test_py_edit_that_breaks_syntax_warns(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    (tmp_path / "a.py").write_text("def f():\n    x = 1\n    return x\n")
    out = await mux.execute("edit replace a.py --lines 2:2", stdin="x = 1")
    assert "WARNING: `a.py` no longer parses" in out.output and "line 2" in out.output
    # already broken before the edit, or not python: no warning
    out = await mux.execute("edit replace a.py --lines 2:2", stdin="  y = 2")
    assert "WARNING" not in out.output
    (tmp_path / "n.txt").write_text("a\nb\n")
    assert "WARNING" not in (await mux.execute("edit replace n.txt --lines 1:1", stdin="(")).output
    (tmp_path / "w.py").write_text("x = 1\n")
    out = await mux.execute("edit write w.py", stdin="def f(:\n")
    assert out.output.endswith("Fix it now.") and "WARNING: `w.py`" in out.output


async def test_search_replace_blocks(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    f = tmp_path / "a.py"
    f.write_text("def f():\n    x = 1\n    y = 2\n    return x\n")
    blk = "<<<<<<< SEARCH\n    x = 1\n=======\n    x = 10\n>>>>>>> REPLACE"
    out = await mux.execute("edit replace a.py", stdin=blk)
    assert out.output == "Replaced 1 block(s) in `a.py`." and "x = 10" in f.read_text()
    two = blk.replace("x = 1", "y = 2") + "\n" + blk.replace("x = 1", "return x")
    assert "Replaced 2 block(s)" in (await mux.execute("edit replace a.py", stdin=two)).output
    # atomic: second block missing -> nothing changed
    before = f.read_text()
    bad = blk.replace("x = 1", "x = 10") + "\n" + blk.replace("x = 1", "nope")
    out = await mux.execute("edit replace a.py", stdin=bad)
    assert "block 2 not found" in out.output and f.read_text() == before
    # ambiguous
    f.write_text("a\na\n")
    out = await mux.execute(
        "edit replace a.py", stdin="<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE"
    )
    assert "matches 2 times" in out.output
    # malformed block, missing file, syntax warning
    assert (
        "no complete" in (await mux.execute("edit replace a.py", stdin="<<<<<<< SEARCH\nx")).output
    )
    out = await mux.execute("edit replace zz.py", stdin=blk)
    assert "not found" in out.output
    f.write_text("def f():\n    return 1\n")
    out = await mux.execute(
        "edit replace a.py",
        stdin="<<<<<<< SEARCH\n    return 1\n=======\nreturn 1\n>>>>>>> REPLACE",
    )
    assert "WARNING" in out.output
