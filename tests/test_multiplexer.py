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


async def test_bash_preserves_quotes_and_shell_syntax(tmp_path: Path) -> None:
    """bash receives the raw command text, so quotes, pipes and && survive (#37)."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["bash"], sandbox=sandbox)
    mux = harness.build_multiplexer("ses_q", ["bash"], sandbox, "ollama/qwen3.5:9b")
    (tmp_path / "f").write_text("a b\n")
    (tmp_path / "app.py").write_text("def f():\n    return list(x)\n    return 1\n")

    await mux.execute("bash sed -i 's/a b/c d/' f")
    assert (tmp_path / "f").read_text() == "c d\n"

    out = await mux.execute('bash grep -n "return list(" app.py')
    assert "2:    return list(x)" in out.output and "return 1" not in out.output

    assert "2" in (await mux.execute('bash python3 -c "print(1+1)"')).output
    assert "2" in (await mux.execute("bash echo a b | wc -w")).output
    assert "x" in (await mux.execute("bash true && echo x")).output
    assert "hi there" in (await mux.execute("bash echo hi there")).output
    assert "IN" in (await mux.execute("bash tr a-z A-Z", stdin="in")).output
    assert "Usage: bash" in (await mux.execute("bash --help")).output
    assert "Usage: bash" in (await mux.execute("bash -h")).output
    assert "missing" in (await mux.execute("bash")).output


async def test_disabled_builtin_vs_unknown_command() -> None:
    mux = Multiplexer()

    @tool(name="ping")
    def ping() -> str:
        return "pong"

    mux.register(ping)
    disabled = await mux.execute("mem recall obs_3")
    assert disabled.is_error and disabled.error_kind == "unknown_cmd"
    assert disabled.output.startswith("Error: `mem` is disabled.")
    assert "Enabled tools: ping." in disabled.output and "--tools" in disabled.output
    assert "tools=[...]" in disabled.output and "`tools:`" in disabled.output
    unknown = await mux.execute("frobnicate now")
    assert unknown.output.startswith("Error: unknown command `frobnicate`.")
    assert "Enabled tools: ping." in unknown.output and "disabled" not in unknown.output
    assert (await mux.execute("ping")).output == "pong"


async def test_heredoc_in_cmd_becomes_stdin(tmp_path: Path) -> None:
    """`edit write f <<'EOF'` works like stdin; bash keeps its own heredoc."""
    from tether.multiplexer import split_heredoc

    assert split_heredoc("edit write f <<'EOF'\nhi\nEOF") == ("edit write f", "hi")
    assert split_heredoc("done") == ("done", None)
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    harness = Harness(db_path=tmp_path / "t.db", tools=["edit", "bash"], sandbox=sandbox)
    mux = harness.build_multiplexer("ses_hd", ["edit", "bash"], sandbox, "ollama/qwen3.5:9b")
    out = await mux.execute("edit write f.txt <<'EOF'\nhello\nEOF")
    assert not out.is_error and (tmp_path / "f.txt").read_text().strip() == "hello"
    out = await mux.execute("bash cat <<'EOF'\nkeep\nEOF")
    assert "keep" in out.output
