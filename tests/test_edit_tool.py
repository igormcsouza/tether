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
    assert out == "Replaced 1 lines with 3 (0 removed, 2 added; first removed: none)"


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
