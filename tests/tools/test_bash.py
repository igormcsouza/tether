"""Unit tests for tether/tools/bash.py (sandboxed shell tool)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy


async def test_bash_tool(tmp_path: Path) -> None:
    """Verify bash --help, missing command error, inline command, and stdin script execution."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "tether.db", tools=["bash"], sandbox=sandbox)
    mux = harness.build_multiplexer("ses_bash", ["bash"], sandbox, "ollama/qwen3.5:9b")

    assert "Usage: bash" in (await mux.execute("bash --help")).output
    assert "Error: missing `<command>`" in (await mux.execute("bash")).output
    assert "hi_bash" in (await mux.execute("bash echo hi_bash")).output
    assert "hi_stdin" in (await mux.execute("bash", stdin="echo hi_stdin")).output
