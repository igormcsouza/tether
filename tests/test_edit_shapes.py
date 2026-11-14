"""F1b (#317): three shapes of a correct edit that tether refused or mis-applied."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy
from tether.context import estimate_tokens

ORIG = "x = 1\ny = 2\nz = 3\n"
HUNK = "@@ -1,3 +1,3 @@\n x = 1\n-y = 2\n+y = 20\n z = 3\n"
HEADED = "--- a.py\n+++ a.py\n" + HUNK


def _mux(tmp_path: Path):  # type: ignore[no-untyped-def]
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit"], sandbox=sandbox)
    return harness.build_multiplexer("ses_shapes", ["edit"], sandbox, "ollama/qwen3.5:9b")


# DoD-1: a unified diff sent to `edit replace <path>` is applied like `edit <path>` applies it.
async def test_headed_diff_via_replace_matches_edit_path(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    mux = _mux(tmp_path)
    target.write_text(ORIG)
    via_path = (await mux.execute("edit a.py", stdin=HEADED)).output
    after_path = target.read_text()
    target.write_text(ORIG)
    via_replace = (await mux.execute("edit replace a.py", stdin=HEADED)).output
    assert via_replace == via_path
    assert target.read_text() == after_path == "x = 1\ny = 20\nz = 3\n"


async def test_headerless_hunks_via_replace_are_applied(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text(ORIG)
    out = (await _mux(tmp_path).execute("edit replace a.py", stdin=HUNK)).output
    assert out.startswith("Patched")
    assert target.read_text() == "x = 1\ny = 20\nz = 3\n"


async def test_diff_via_replace_that_does_not_match_changes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text(ORIG)
    bad = "@@ -1 +1 @@\n-nope\n+yes\n"
    out = (await _mux(tmp_path).execute("edit replace a.py", stdin=bad)).output
    assert "not found" in out
    assert target.read_text() == ORIG


async def test_search_replace_works_via_replace_without_lines(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text(ORIG)
    stdin = "<<<<<<< SEARCH\ny = 2\n=======\ny = 5\n>>>>>>> REPLACE\n"
    out = (await _mux(tmp_path).execute("edit replace a.py", stdin=stdin)).output
    assert out.startswith("Replaced 1 block")
    assert target.read_text() == "x = 1\ny = 5\nz = 3\n"


# DoD-2: a `, stdin="..."` tail typed inside cmd is moved into stdin.
async def test_stdin_tail_inside_cmd_is_moved_to_stdin(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text(ORIG)
    cmd = 'edit replace f.py --lines 2:2, stdin="x = 2"'
    out = (await _mux(tmp_path).execute(cmd)).output
    assert "Replaced lines 2:2" in out
    assert (tmp_path / "f.py").read_text() == "x = 1\nx = 2\nz = 3\n"


async def test_stdin_tail_unescapes_newlines_and_quotes(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text(ORIG)
    cmd = r'edit replace f.py --lines 2:2, stdin="y = \"a\"\nw = 3"'
    await _mux(tmp_path).execute(cmd)
    assert (tmp_path / "f.py").read_text() == 'x = 1\ny = "a"\nw = 3\nz = 3\n'


async def test_real_stdin_wins_over_cmd_tail(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text(ORIG)
    cmd = 'edit replace f.py --lines 2:2, stdin="x = 2"'
    await _mux(tmp_path).execute(cmd, stdin="y = 9\n")
    assert (tmp_path / "f.py").read_text() == "x = 1\ny = 9\nz = 3\n"


# DoD-3: a marked diff of exactly the lines a:b is applied as a diff.
async def test_marked_diff_of_exact_lines_is_applied(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text(ORIG)
    await _mux(tmp_path).execute("edit replace f.py --lines 2:2", stdin="-y = 2\n+y = 20\n")
    assert (tmp_path / "f.py").read_text() == "x = 1\ny = 20\nz = 3\n"


async def test_markdown_list_stays_literal(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("intro\nold\noutro\n")
    await _mux(tmp_path).execute("edit replace notes.md --lines 2:2", stdin="- one\n- two\n")
    assert (tmp_path / "notes.md").read_text() == "intro\n- one\n- two\noutro\n"


async def test_minus_text_not_matching_the_file_stays_literal(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text(ORIG)
    await _mux(tmp_path).execute("edit replace f.py --lines 2:2", stdin="-zzz\n+y = 20\n")
    assert (tmp_path / "f.py").read_text() == "x = 1\n-zzz\n+y = 20\nz = 3\n"


# DoD-4: the help keeps the SEARCH/REPLACE markers, every verb, and the token budget.
async def test_edit_help_names_markers_and_verbs(tmp_path: Path) -> None:
    help_text = (await _mux(tmp_path).execute("edit --help")).output
    for marker in ("<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE"):
        assert marker in help_text
    usage = help_text.splitlines()[0]
    for verb in ("view", "write", "append", "insert", "replace"):
        assert verb in usage
    assert estimate_tokens(help_text) <= 60
