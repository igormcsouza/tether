"""`edit insert <path> --line N` adds lines before line N and replaces nothing (F1a, #320)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy


def _mux(tmp_path: Path):  # type: ignore[no-untyped-def]
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit"], sandbox=sandbox)
    return harness.build_multiplexer("ses_insert", ["edit"], sandbox, "ollama/qwen3.5:9b")


async def test_insert_adds_lines_before_n_and_keeps_every_line(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    out = (await _mux(tmp_path).execute("edit insert f.txt --line 2", stdin="X\nY\n")).output
    assert out == "Inserted 2 lines before line 2 in `f.txt` (5 lines now)."
    assert (tmp_path / "f.txt").read_text() == "a\nX\nY\nb\nc\n"


async def test_insert_at_length_plus_one_appends(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\n")
    await _mux(tmp_path).execute("edit insert f.txt --line 3", stdin="c\n")
    assert (tmp_path / "f.txt").read_text() == "a\nb\nc\n"


async def test_insert_into_empty_file_at_line_one(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    out = (await _mux(tmp_path).execute("edit insert f.txt --line 1", stdin="x\n")).output
    assert out == "Inserted 1 lines before line 1 in `f.txt` (1 lines now)."
    assert (tmp_path / "f.txt").read_text() == "x\n"


async def test_insert_adds_final_newline_when_stdin_has_none(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\n")
    await _mux(tmp_path).execute("edit insert f.txt --line 3", stdin="c")
    assert (tmp_path / "f.txt").read_text() == "a\nb\nc\n"


async def test_insert_bad_input_changes_nothing(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\n")
    mux = _mux(tmp_path)
    cases = [
        ("edit insert f.txt", "x\n", "needs `--line N`"),
        ("edit insert f.txt --line", "x\n", "needs a number"),
        ("edit insert f.txt --line x", "x\n", "must be an integer"),
        ("edit insert f.txt --line 0", "x\n", "between 1 and 3"),
        ("edit insert f.txt --line -1", "x\n", "between 1 and 3"),
        ("edit insert f.txt --line 9", "x\n", "between 1 and 3"),
        ("edit insert f.txt --line 2", None, "the lines to add in `stdin`"),
        ("edit insert missing.txt --line 1", "x\n", "not found"),
    ]
    for cmd, stdin, hint in cases:
        out = (await mux.execute(cmd, stdin=stdin)).output
        assert out.startswith("Error: "), (cmd, out)
        assert hint in out, (cmd, out)
    assert (tmp_path / "f.txt").read_text() == "a\nb\n"


async def test_insert_outside_workspace_is_a_sandbox_violation(tmp_path: Path) -> None:
    out = (await _mux(tmp_path).execute("edit insert ../x.txt --line 1", stdin="x\n")).output
    assert "Sandbox violation" in out


async def test_insert_that_breaks_python_warns(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def f():\n    return 1\n")
    out = (await _mux(tmp_path).execute("edit insert m.py --line 2", stdin="  x = (\n")).output
    assert "WARNING" in out
    assert "m.py" in out


async def test_bare_lines_deletes_and_says_so(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n")
    out = (await _mux(tmp_path).execute("edit replace f.txt --lines 2:2", stdin="")).output
    assert out == (
        "Deleted lines 2:2 in `f.txt` (empty stdin). To replace them, send the new text in stdin."
    )
    assert (tmp_path / "f.txt").read_text() == "a\nc\n"


async def test_replace_with_text_keeps_old_message(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\n")
    out = (await _mux(tmp_path).execute("edit replace f.txt --lines 2:2", stdin="B\n")).output
    assert out == "Replaced lines 2:2 in `f.txt` with 1 lines."


async def test_append_without_final_newline_gets_one(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\n")
    await _mux(tmp_path).execute("edit append f.txt", stdin="b")
    assert (tmp_path / "f.txt").read_text() == "a\nb\n"


async def test_insert_help_names_the_verb(tmp_path: Path) -> None:
    assert "insert" in (await _mux(tmp_path).execute("edit --help")).output
