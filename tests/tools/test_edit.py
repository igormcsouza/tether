"""Unit tests for tether/tools/edit.py (workspace-jailed file view, write, replace)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy


async def test_edit_tool(tmp_path: Path) -> None:
    """Verify edit view, write, replace, line range validation, and sandbox enforcement."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "tether.db", tools=["edit"], sandbox=sandbox)
    mux = harness.build_multiplexer("ses_edit", ["edit"], sandbox, "ollama/qwen3.5:9b")

    assert "Usage: edit" in (await mux.execute("edit --help")).output
    assert "Error: missing `<path>`" in (await mux.execute("edit view")).output
    assert "not found" in (await mux.execute("edit view missing.txt")).output
    assert "Error: missing `<path>`" in (await mux.execute("edit write")).output
    assert "requires file content" in (await mux.execute("edit write a.txt")).output

    res_write = await mux.execute("edit write a.txt", stdin="l1\nl2\nl3\n")
    assert "Wrote" in res_write.output
    assert "l2" in (await mux.execute("edit view a.txt --lines 2")).output

    res_rep = await mux.execute("edit replace a.txt --lines 2:2", stdin="updated line 2")
    assert "Replaced lines 2:2" in res_rep.output
    assert "updated line 2" in (await mux.execute("edit view a.txt --lines 1:3")).output

    assert "Error: invalid line range" in (await mux.execute("edit view a.txt --lines bad")).output
    assert "Error: invalid line range" in (await mux.execute("edit view a.txt --lines a:b")).output
    assert "requires `start:end`" in (await mux.execute("edit view a.txt --lines")).output
    assert "requires `<path>" in (await mux.execute("edit replace a.txt")).output
    assert "requires replacement" in (await mux.execute("edit replace a.txt --lines 1:1")).output
    assert "not found" in (await mux.execute("edit replace nope.txt --lines 1:1", stdin="x")).output
    assert (
        "requires `start:end`"
        in (await mux.execute("edit replace a.txt --lines", stdin="x")).output
    )
    assert (
        "Error: invalid line range"
        in (await mux.execute("edit replace a.txt --lines x:y", stdin="x")).output
    )
    assert "Error: unknown subcommand" in (await mux.execute("edit bogus")).output
    assert "Sandbox violation" in (await mux.execute("edit view ../.env")).output
