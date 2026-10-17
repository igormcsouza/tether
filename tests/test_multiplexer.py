"""Unit tests for tether/multiplexer.py (act command normalization, routing, and error handling)."""

from __future__ import annotations

from tether import tool
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
