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


async def test_search_replace_tolerates_missing_final_marker(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    f = tmp_path / "a.txt"
    f.write_text("a\nb\n")
    out = await mux.execute("edit replace a.txt", stdin="<<<<<<< SEARCH\na\n=======\nA")
    assert out.output == "Replaced 1 block(s) in `a.txt`." and f.read_text() == "A\nb\n"
    # a truncated block in the middle must not swallow the next one
    two = "<<<<<<< SEARCH\nb\n=======\nB\n<<<<<<< SEARCH\nA\n=======\nZ\n>>>>>>> REPLACE"
    out = await mux.execute("edit replace a.txt", stdin=two)
    assert "block 1 is missing its `>>>>>>> REPLACE`" in out.output and f.read_text() == "A\nb\n"


async def test_verbless_edit_infers_view_write_replace(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    assert "Wrote" in (await mux.execute("edit a.txt", stdin="one\ntwo\n")).output
    assert "   2: two" in (await mux.execute("edit a.txt")).output
    swap = "<<<<<<< SEARCH\none\n=======\nONE\n>>>>>>> REPLACE"
    assert "Replaced 1 block" in (await mux.execute("edit a.txt", stdin=swap)).output
    assert (tmp_path / "a.txt").read_text() == "ONE\ntwo\n"
    assert "   1: ONE" in (await mux.execute("edit --path a.txt --line_start 1")).output
    assert (
        "   2: two" in (await mux.execute("edit --path 'a.txt' --line_start 2 --line_end 2")).output
    )
    assert "unknown subcommand" in (await mux.execute("edit nothing")).output
    assert "unknown subcommand" in (await mux.execute("edit --bogus x")).output


PATCH = """*** Begin Patch
*** Update File: a.py
@@ def f
 def f():
-    return 1
+    return 2
*** Add File: sub/b.txt
+hello
*** Delete File: gone.txt
*** End Patch"""


async def test_apply_patch_update_add_delete(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    (tmp_path / "gone.txt").write_text("x")
    out = (await mux.execute("apply_patch", stdin=PATCH)).output
    assert out == "Patched: update a.py, add sub/b.txt, delete gone.txt."
    assert (tmp_path / "a.py").read_text() == "def f():\n    return 2\n"
    assert (tmp_path / "sub/b.txt").read_text() == "hello\n" and not (
        tmp_path / "gone.txt"
    ).exists()
    heredoc = (
        "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: sub/b.txt\n-hello\n+bye\n"
        "*** End Patch\nEOF"
    )
    assert "Patched" in (await mux.execute(heredoc)).output
    assert (tmp_path / "sub/b.txt").read_text() == "bye\n"
    (tmp_path / "w.py").write_text("x = 1\n")
    broke = "*** Begin Patch\n*** Update File: w.py\n-x = 1\n+x = (\n*** End Patch"
    assert "no longer parses" in (await mux.execute("edit apply_patch", stdin=broke)).output


async def test_apply_patch_errors_change_nothing(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    (tmp_path / "a.py").write_text("x\nx\n")
    run = lambda p: mux.execute("apply_patch", stdin=p)  # noqa: E731
    assert "Begin Patch" in (await run("nope")).output
    assert "Begin Patch" in (await run("")).output
    assert "no `*** Update" in (await run("*** Begin Patch\n*** End Patch")).output
    assert (
        "not found; nothing"
        in (await run("*** Begin Patch\n*** Update File: z.py\n-a\n*** End Patch")).output
    )
    miss = "*** Begin Patch\n*** Add File: n.txt\n+n\n*** Update File: a.py\n-y\n+z\n*** End Patch"
    assert "hunk 1 of `a.py` not found" in (await run(miss)).output
    assert not (tmp_path / "n.txt").exists()
    twice = "*** Begin Patch\n*** Update File: a.py\n-x\n+z\n*** End Patch"
    assert "matches 2 times" in (await run(twice)).output
    append = "*** Begin Patch\n*** Update File: a.py\n+tail\n*** End Patch"
    assert "Patched" in (await run(append)).output
    assert (tmp_path / "a.py").read_text() == "x\nx\ntail\n"


async def test_apply_patch_multiple_hunks_and_bare_context(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    (tmp_path / "m.txt").write_text("a\nb\nc\nd\n")
    patch = (
        "*** Begin Patch\n*** Update File: m.txt\n@@\n-a\n+A\n@@ later\nc\n-d\n+D\n*** End Patch"
    )
    assert "Patched" in (await mux.execute("apply_patch", stdin=patch)).output
    assert (tmp_path / "m.txt").read_text() == "A\nb\nc\nD\n"


async def test_apply_patch_text_inside_cmd_or_bash_stdin(tmp_path: Path) -> None:
    mux = _mux(tmp_path)
    (tmp_path / "p.txt").write_text("one\n")
    body = "*** Begin Patch\n*** Update File: p.txt\n-one\n+two\n*** End Patch"
    assert "Patched" in (await mux.execute(f"apply_patch\n{body}")).output
    assert (tmp_path / "p.txt").read_text() == "two\n"
    second = "*** Begin Patch\n*** Update File: p.txt\n-two\n+three\n*** End Patch"
    shell = f"apply_patch <<'PATCH'\n{second}\nPATCH"
    assert "Patched" in (await mux.execute("bash", stdin=shell)).output
    assert (tmp_path / "p.txt").read_text() == "three\n"


async def test_unified_diff_stdin_is_applied_not_written(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    diff = "--- a.py\n+++ a.py\n@@ -1,3 +1,3 @@\n x = 1\n-y = 2\n+y = 20\n z = 3\n"
    mux = _mux(tmp_path)
    out = (await mux.execute("edit a.py", stdin=diff)).output
    assert out.startswith("Patched: update a.py")
    assert (tmp_path / "a.py").read_text() == "x = 1\ny = 20\nz = 3\n"
    git = (
        "diff --git a/a.py b/a.py\nindex 1..2 100644\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 9\n"
    )
    assert (await mux.execute("edit apply_patch", stdin=git)).output.startswith("Patched")
    assert (tmp_path / "a.py").read_text().startswith("x = 9\n")
    bad = "--- a.py\n+++ a.py\n@@ -1 +1 @@\n-nope\n+yes\n"
    assert "not found" in (await mux.execute("edit a.py", stdin=bad)).output
