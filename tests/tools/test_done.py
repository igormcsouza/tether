"""Unit tests for tether/tools/done.py (mandatory explicit termination primitive)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy


async def test_done_tool(tmp_path: Path) -> None:
    """Verify done --help, missing argument error, inline answer, and stdin deliverable."""
    harness = Harness(db_path=tmp_path / "tether.db")
    mux = harness.build_multiplexer(
        session_id="ses_done",
        enabled_tools=[],
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model="ollama/qwen3.5:9b",
    )
    assert "Usage: done" in (await mux.execute("done --help")).output
    assert "Error:" in (await mux.execute("done")).output
    res_inline = await mux.execute("done 'short'")
    assert res_inline.is_done and res_inline.output == "short"
    res_stdin = await mux.execute("done", stdin="Full markdown report")
    assert res_stdin.is_done and res_stdin.output == "Full markdown report"
