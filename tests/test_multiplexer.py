"""Unit tests for tether/multiplexer.py (act command normalization, routing, and error handling)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy, tool
from tether.multiplexer import Multiplexer, normalize_cmd, split_cli


async def test_multiplexer_normalization_and_dispatch() -> None:
    """Verify command normalization, help routing, unknown commands, and exception handling."""
    assert normalize_cmd("```bash\nweb search ai\n```") == "web search ai"
    assert normalize_cmd("`web search ai`") == "web search ai"
    assert normalize_cmd("$ web search ai") == "web search ai"
    assert normalize_cmd("> web search ai") == "web search ai"
    assert normalize_cmd("tether web search ai") == "web search ai"
    assert split_cli('web search "unclosed quote') == ["web", "search", "unclosed", "quote"]

    mux = Multiplexer()
    mux.register(lambda a: a)

    @tool(name="sample-cmd", description="Sample command")
    def sample_cmd(arg: str) -> str:
        return arg

    mux.register(sample_cmd)

    assert (await mux.execute("   ")).is_error
    assert (await mux.execute('""')).is_error
    res_quote_only = await mux.execute('"')
    assert res_quote_only.is_error and "empty command" in res_quote_only.output

    assert "Available commands:" in (await mux.execute("help")).output
    assert "Usage:" in (await mux.execute("help sample-cmd")).output
    assert (await mux.execute("unknown-cmd")).is_error

    @tool(name="boom")
    def boom() -> str:
        raise RuntimeError("kaboom")

    mux.register(boom)
    assert "Error executing `boom`: kaboom" in (await mux.execute("boom")).output


async def test_literal_newline_stdin_normalized(tmp_path: Path) -> None:
    """Escaped one-line stdin is unescaped for edit write/replace and done only."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit", "bash"], sandbox=sandbox)
    mux = harness.build_multiplexer("ses_nl", ["edit", "bash"], sandbox, "ollama/qwen3.5:9b")

    await mux.execute("edit write a.txt", stdin="l1\\nl2\\tx")
    assert (tmp_path / "a.txt").read_text() == "l1\nl2\tx"

    await mux.execute("edit replace a.txt --lines 1:1", stdin="r1\\nr2")
    assert (tmp_path / "a.txt").read_text().startswith("r1\nr2\n")

    done = await mux.execute("done", stdin="# T\\n\\nbody")
    assert done.final_result == "# T\n\nbody"

    # real newlines untouched, even if a literal \n also appears
    await mux.execute("edit write b.txt", stdin="a\\nb\nc")
    assert (tmp_path / "b.txt").read_text() == "a\\nb\nc"

    # legit single line without \n untouched
    await mux.execute("edit write c.txt", stdin="C:\\temp")
    assert (tmp_path / "c.txt").read_text() == "C:\\temp"

    # bash stdin untouched
    out = await mux.execute("bash cat", stdin="x\\ny")
    assert "x\\ny" in out.output
