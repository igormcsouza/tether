"""Comprehensive integration and edge-case test suite for 100% Tether coverage."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest

from tether import (
    ActionCall,
    Harness,
    ModelResponse,
    SandboxPolicy,
    SandboxViolationError,
    SkillLoader,
    SQLiteStore,
    extract_fallback_action,
    register_provider,
    tool,
)
from tether.cli import _async_main, main
from tether.context import ContextAssembler, estimate_messages_tokens, estimate_tokens
from tether.decorator import ToolSpec, build_tool_spec
from tether.harness import spawn_detached_worker
from tether.multiplexer import Multiplexer, normalize_cmd, split_cli
from tether.providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    parse_tool_arguments,
    resolve_provider,
)
from tether.tools.web import _format_results, _unwrap_ddg_url, html_to_markdown


async def test_providers_http_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Ollama, OpenAI, and Anthropic providers via httpx.MockTransport."""
    # 1. resolve_provider routing & errors
    assert isinstance(resolve_provider("qwen3.5:9b"), OllamaProvider)
    assert isinstance(resolve_provider("openai/gpt-4o-mini"), OpenAIProvider)
    assert isinstance(resolve_provider("anthropic/claude-3-7-sonnet-latest"), AnthropicProvider)
    with pytest.raises(ValueError, match="Provider prefix cannot be empty"):
        register_provider("  / ", lambda m: OllamaProvider(m))
    with pytest.raises(ValueError, match="Unknown model provider"):
        resolve_provider("unknown_vendor/model")

    # 2. OllamaProvider: 404 model fallback + direct tool call + dict/str fallback
    ollama_step = 0

    def ollama_handler(request: httpx.Request) -> httpx.Response:
        nonlocal ollama_step
        if request.url.path == "/api/tags":
            if ollama_step == 1:
                return httpx.Response(
                    200, json={"models": [{"name": "gemma4:e4b"}, {"name": "qwen3.5:9b"}]}
                )
            if ollama_step == 2:
                return httpx.Response(200, json={"models": [{"name": "gemma4:e4b"}]})
            if ollama_step == 3:
                return httpx.Response(200, json={"models": []})
            return httpx.Response(500)

        ollama_step += 1
        if ollama_step == 1:
            return httpx.Response(404)
        if ollama_step == 2:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "act", "arguments": {"cmd": "done 'ok'"}}}
                        ],
                    },
                    "prompt_eval_count": 50,
                    "eval_count": 10,
                },
            )
        if ollama_step == 3:
            # Direct non-act tool call with dict arguments
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "web", "arguments": {"q": "ai"}}}],
                    }
                },
            )
        if ollama_step == 4:
            # Direct non-act tool call with string arguments
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "web", "arguments": "raw"}}],
                    }
                },
            )
        return httpx.Response(
            200,
            json={"message": {"content": 'act("done", stdin="from text")'}},
        )

    client_ollama = httpx.AsyncClient(transport=httpx.MockTransport(ollama_handler))
    op = OllamaProvider("missing:model", client=client_ollama)
    r1 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert op.model_name == "qwen3.5:9b"
    assert r1.action is not None and r1.action.cmd == "done 'ok'"
    assert r1.prompt_tokens == 60

    # Test _resolve_installed_model non-qwen, empty, and exception paths
    ollama_step = 2
    assert await op._resolve_installed_model(client_ollama) == "gemma4:e4b"
    ollama_step = 3
    assert await op._resolve_installed_model(client_ollama) is None
    ollama_step = 4
    assert await op._resolve_installed_model(client_ollama) is None

    ollama_step = 2
    r2 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert r2.action is not None and "web --q 'ai'" in r2.action.cmd
    r3 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert r3.action is not None and r3.action.cmd == "web"
    r4 = await op.generate([{"role": "user", "content": "hi"}], [])
    assert r4.action is not None and r4.action.stdin == "from text"
    await op.aclose()

    # 3. OpenAIProvider
    oai_calls = 0

    def openai_handler(request: httpx.Request) -> httpx.Response:
        nonlocal oai_calls
        oai_calls += 1
        assert request.headers.get("Authorization") == "Bearer test-key"
        if oai_calls == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "act",
                                            "arguments": '{"cmd": "done", "stdin": "oai"}',
                                        }
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 77},
                },
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": 'act("done", stdin="fallback")'}}]},
        )

    oai_client = httpx.AsyncClient(transport=httpx.MockTransport(openai_handler))
    oai = OpenAIProvider("gpt-4o-mini", api_key="test-key", client=oai_client)
    assert oai._get_client() is oai_client
    or1 = await oai.generate([{"role": "user", "content": "hi"}], [])
    assert or1.action is not None and or1.action.stdin == "oai"
    assert or1.prompt_tokens == 77
    or2 = await oai.generate([{"role": "user", "content": "hi"}], [])
    assert or2.action is not None and or2.action.stdin == "fallback"
    await oai.aclose()
    # Re-creating client after close
    c_new = oai._get_client()
    assert not c_new.is_closed
    await oai.aclose()

    # 4. AnthropicProvider
    anth_calls = 0

    def anthropic_handler(request: httpx.Request) -> httpx.Response:
        nonlocal anth_calls
        anth_calls += 1
        assert request.headers.get("anthropic-workspace-id") == "ws_123"
        if anth_calls == 1:
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "Thinking..."},
                        {"type": "tool_use", "input": {"cmd": "done", "stdin": "claude_ok"}},
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 25},
                },
            )
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": 'act("done", stdin="anth_fb")'}]},
        )

    anth_client = httpx.AsyncClient(transport=httpx.MockTransport(anthropic_handler))
    anth = AnthropicProvider(
        "claude-3-7-sonnet-latest",
        api_key="ak",
        workspace_id="ws_123",
        client=anth_client,
    )
    ar1 = await anth.generate(
        [
            {"role": "system", "content": "Sys"},
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
        ],
        [{"function": {"name": "act", "description": "d", "parameters": {}}}],
    )
    assert ar1.action is not None and ar1.action.stdin == "claude_ok"
    assert ar1.prompt_tokens == 125
    ar2 = await anth.generate([{"role": "user", "content": "Hi"}], [])
    assert ar2.action is not None and ar2.action.stdin == "anth_fb"
    await anth.aclose()
    c_anth_new = anth._get_client()
    assert not c_anth_new.is_closed
    await anth.aclose()


def test_base_parser_and_context_edge_cases() -> None:
    """Cover all fallback parser branches in base.py and context.py."""
    assert parse_tool_arguments("not json") is None
    assert parse_tool_arguments("[1, 2, 3]") is None
    assert parse_tool_arguments({"other": 1}) is None
    c_cmd = parse_tool_arguments({"command": "web search ai", "stdin": " body "})
    assert c_cmd is not None and c_cmd.cmd == "web search ai"

    assert extract_fallback_action("") is None
    assert extract_fallback_action("<tool_call>not json</tool_call>") is None
    assert extract_fallback_action('Here is JSON: {"cmd": "done", "stdin": "raw_json"}') is not None
    assert extract_fallback_action('{"cmd": ""}') is None

    # AST single-line fallback branches (when quotes differ or keyword args used)
    ast1 = extract_fallback_action("act(cmd='done', stdin='via_kw')")
    assert ast1 is not None and ast1.cmd == "done" and ast1.stdin == "via_kw"
    ast2 = extract_fallback_action("act('done', 'pos_stdin')")
    assert ast2 is not None and ast2.cmd == "done" and ast2.stdin == "pos_stdin"
    ast3 = extract_fallback_action("act(command='done')")
    assert ast3 is not None and ast3.cmd == "done"
    assert extract_fallback_action("act(invalid syntax ===)") is None
    assert extract_fallback_action("no action here") is None

    # context.py edge cases
    assert estimate_tokens("") == 0
    msgs = [{"role": "assistant", "content": "hi", "tool_calls": [{"name": "act"}]}]
    assert estimate_messages_tokens(msgs) > 4

    ca = ContextAssembler(max_context_tokens=50)
    p1 = ca.build_system_prompt("- done: finish", skill_instructions="Be concise.")
    p2 = ca.build_system_prompt("- done: finish")
    assert p1 == p2 and "[SKILL]" in p1

    # ContextAssembler with pins when history ends with assistant message & token eviction
    from tether.store import TurnRecord

    turns = [
        TurnRecord(1, "s", 1, "user", "long text " * 30, None, None, None, 0.0),
        TurnRecord(2, "s", 1, "assistant", "resp", "web search", "stdin_payload", None, 0.0),
        TurnRecord(3, "s", 2, "user", "more text " * 30, None, None, None, 0.0),
        TurnRecord(4, "s", 2, "assistant", "thinking", None, None, None, 0.0),
    ]
    assembled = ca.assemble(
        system_prompt="Sys",
        goal="Goal",
        turns=turns,
        observations={},
        pins={"k": "v"},
        current_step=3,
    )
    assert "[PINNED MEMORY]" in assembled[-1]["content"]


async def test_decorator_multiplexer_and_tools_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover decorator.py, multiplexer.py, done.py, bash.py, edit.py, mem.py, skills.py."""

    @tool
    def sample_cmd(
        mode: Literal["fast", "accurate"],
        count: int,
        ratio: float,
        flag: bool = False,
        label: str = "default",
        stdin: str | None = None,
    ) -> str:
        return f"{mode}:{count}:{ratio}:{flag}:{label}:{stdin or ''}"

    sample_cmd.__doc__ = "X" * 120

    mux = Multiplexer()
    spec = mux.register(sample_cmd)
    assert mux.get_tool("sample-cmd") is spec
    assert "sample-cmd" in mux.tool_names
    assert "..." in spec.help_text()

    # Variadic ParamSpec help and parsing
    from tether.decorator import ParamSpec

    var_spec = ToolSpec(
        name="var-cmd",
        description="Variadic command",
        fn=lambda **kw: str(kw.get("items", "")),
        params=[ParamSpec("items", "--items", "str", str, True, None, is_variadic=True)],
        accepts_stdin=False,
        is_async=False,
    )
    mux.register(var_spec)
    assert "<items...>" in var_spec.help_text()
    assert (await mux.execute("var-cmd one two three")).output == "one two three"

    # Async @tool function test
    @tool(name="async-echo")
    async def async_echo(msg: str) -> str:
        return f"async:{msg}"

    mux.register(async_echo)
    assert (await mux.execute("async-echo hello")).output == "async:hello"

    # Long description truncation in index_line
    long_spec = build_tool_spec(lambda x: x, name="long-tool", description="A" * 60)
    assert long_spec.index_line().endswith("...")

    # Broken type hints fallback in build_tool_spec
    def broken_hints(x: NonExistentType) -> str:  # type: ignore[name-defined] # noqa: F821
        return x

    bh_spec = build_tool_spec(broken_hints)
    assert bh_spec.params[0].type_name == "str"

    # Single required string param satisfied via stdin
    @tool(name="single-str")
    def single_str(payload: str) -> str:
        return f"got:{payload}"

    mux.register(single_str)
    r_stdin = await mux.execute("single-str", stdin="hello_stdin")
    assert r_stdin.output == "got:hello_stdin"
    assert "missing required argument" in (await mux.execute("single-str")).output

    # Trailing unquoted words joined into last string param
    @tool(name="greet")
    def greet(name: str) -> str:
        return f"hi {name}"

    mux.register(greet)
    r_greet = await mux.execute("greet Alice Bob Carol")
    assert r_greet.output == "hi Alice Bob Carol"

    # Unexpected positional arguments when last param is int
    @tool(name="add-int")
    def add_int(x: int) -> str:
        return str(x)

    mux.register(add_int)
    r_unexpected = await mux.execute("add-int 1 2 3")
    assert "Error: unexpected positional arguments" in r_unexpected.output

    # Flag parsing variations
    assert (
        "fast:5:1.5:True:lbl:in"
        in (await mux.execute("sample-cmd fast 5 1.5 --flag true --label=lbl", stdin="in")).output
    )
    assert (
        "fast:5:1.5:True:default:"
        in (await mux.execute("sample-cmd --mode fast --count 5 --ratio 1.5 --flag")).output
    )
    assert (
        "fast:5:1.5:False:default:"
        in (await mux.execute("sample-cmd fast 5 1.5 --flag=false")).output
    )
    assert "unknown flag" in (await mux.execute("sample-cmd --nope 1")).output
    assert "requires a value" in (await mux.execute("sample-cmd --count")).output
    assert "must be one of" in (await mux.execute("sample-cmd invalid 5 1.5")).output
    assert "expects int" in (await mux.execute("sample-cmd fast bad 1.5")).output
    assert "expects float" in (await mux.execute("sample-cmd fast 5 bad")).output
    assert "expects bool" in (await mux.execute("sample-cmd fast 5 1.5 --flag=maybe")).output
    assert "expects int" in (await mux.execute("sample-cmd --count=bad fast 1.5")).output

    # Multiplexer normalize_cmd & execute edge cases
    assert normalize_cmd("```bash\nweb search ai\n```") == "web search ai"
    assert normalize_cmd("`web search ai`") == "web search ai"
    assert normalize_cmd("$ web search ai") == "web search ai"
    assert normalize_cmd("> web search ai") == "web search ai"
    assert normalize_cmd("tether web search ai") == "web search ai"
    assert split_cli('web search "unclosed quote') == ["web", "search", "unclosed", "quote"]

    assert (await mux.execute("   ")).is_error
    assert (await mux.execute('""')).is_error
    assert "Available commands:" in (await mux.execute("help")).output
    assert "Usage:" in (await mux.execute("help sample-cmd")).output
    assert (await mux.execute("unknown-cmd")).is_error

    @tool(name="boom")
    def boom() -> str:
        raise RuntimeError("kaboom")

    mux.register(boom)
    assert "Error executing `boom`: kaboom" in (await mux.execute("boom")).output

    # Built-in tools: done, bash, edit, mem, skill
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    srec = store.create_session("Tool test")
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    h = Harness(
        db_path=tmp_path / "tether.db",
        tools="all",
        sandbox=sandbox,
        skill_search_dirs=[tmp_path / "empty_skills"],
    )
    full_mux = h.build_multiplexer(srec.id, ["all"], sandbox, srec.model)

    # done
    assert "Usage: done" in (await full_mux.execute("done --help")).output
    assert "Error:" in (await full_mux.execute("done")).output
    assert (await full_mux.execute("done 'short'")).is_done

    # bash
    assert "Usage: bash" in (await full_mux.execute("bash --help")).output
    assert "Error: missing `<command>`" in (await full_mux.execute("bash")).output
    assert "hi_bash" in (await full_mux.execute("bash echo hi_bash")).output
    assert "hi_stdin" in (await full_mux.execute("bash", stdin="echo hi_stdin")).output

    # edit
    assert "Usage: edit" in (await full_mux.execute("edit --help")).output
    assert "Error: missing `<path>`" in (await full_mux.execute("edit view")).output
    assert "not found" in (await full_mux.execute("edit view missing.txt")).output
    assert "Error: missing `<path>`" in (await full_mux.execute("edit write")).output
    assert "requires file content" in (await full_mux.execute("edit write a.txt")).output
    await full_mux.execute("edit write a.txt", stdin="l1\nl2\nl3\n")
    assert "l2" in (await full_mux.execute("edit view a.txt --lines 2")).output
    assert (
        "Error: invalid line range"
        in (await full_mux.execute("edit view a.txt --lines bad")).output
    )
    assert (
        "Error: invalid line range"
        in (await full_mux.execute("edit view a.txt --lines a:b")).output
    )
    assert "requires `start:end`" in (await full_mux.execute("edit view a.txt --lines")).output
    assert "requires `<path>" in (await full_mux.execute("edit replace a.txt")).output
    assert (
        "requires replacement" in (await full_mux.execute("edit replace a.txt --lines 1:1")).output
    )
    assert (
        "not found"
        in (await full_mux.execute("edit replace nope.txt --lines 1:1", stdin="x")).output
    )
    assert (
        "requires `start:end`"
        in (await full_mux.execute("edit replace a.txt --lines", stdin="x")).output
    )
    assert (
        "Error: invalid line range"
        in (await full_mux.execute("edit replace a.txt --lines x:y", stdin="x")).output
    )
    assert "Error: unknown subcommand" in (await full_mux.execute("edit bogus")).output
    # Sandbox violation caught by multiplexer
    assert "Sandbox violation" in (await full_mux.execute("edit view ../.env")).output

    # mem
    assert "Usage: mem" in (await full_mux.execute("mem --help")).output
    assert "No pinned facts." in (await full_mux.execute("mem list")).output
    assert "Error: missing `<key>`" in (await full_mux.execute("mem pin")).output
    assert "Error: missing `<val>`" in (await full_mux.execute("mem pin k1")).output
    assert "Pinned `k1`" in (await full_mux.execute("mem pin k1", stdin="v1")).output
    assert "k1: v1" in (await full_mux.execute("mem list")).output
    assert "Error: missing `<key>`" in (await full_mux.execute("mem unpin")).output
    assert "Unpinned `k1`" in (await full_mux.execute("mem unpin k1")).output
    assert "not found" in (await full_mux.execute("mem unpin k1")).output
    obs = store.add_observation(srec.id, 1, "web search", "Quantum computing breakthroughs 2026")
    assert "Error: missing `<query>`" in (await full_mux.execute("mem search")).output
    assert "expects an integer" in (await full_mux.execute("mem search q --top bad")).output
    assert (
        "Quantum" in (await full_mux.execute(f"mem search Quantum --obs {obs.id} --top 2")).output
    )
    assert "No matching chunks" in (await full_mux.execute("mem search nonexistent_xyz")).output
    assert "Error: missing `<obs_id>`" in (await full_mux.execute("mem recall")).output
    assert "not found" in (await full_mux.execute("mem recall obs_999")).output
    assert "Quantum" in (await full_mux.execute(f"mem recall {obs.id}")).output
    assert "Error: unknown subcommand" in (await full_mux.execute("mem bogus")).output

    # skill tool
    assert "Usage: skill" in (await full_mux.execute("skill --help")).output
    assert "No skills found" in (await full_mux.execute("skill list")).output
    assert "Error: missing `<name>`" in (await full_mux.execute("skill load")).output
    assert "not found" in (await full_mux.execute("skill load nope")).output
    assert "Error: unknown subcommand" in (await full_mux.execute("skill bogus")).output

    # Single-file skill discovery & loading
    sk_dir = tmp_path / "my_skills"
    sk_dir.mkdir()
    (sk_dir / "quick.md").write_text(
        "---\nname: quick\ndescription: Quick skill\ntools: web, mem\n---\nInstructions here.",
        encoding="utf-8",
    )
    loader2 = SkillLoader(search_dirs=[sk_dir])
    sk_mux = Multiplexer()
    from tether.skills import _load_tools_module, make_skill_tool

    sk_mux.register(make_skill_tool(loader2, sk_mux))
    assert "quick: Quick skill" in (await sk_mux.execute("skill list")).output
    assert "[Skill `quick` loaded]" in (await sk_mux.execute("skill load quick")).output
    assert _load_tools_module(tmp_path / "nonexistent_file.xyz") == []
    assert SkillLoader().search_dirs  # default search_dirs


async def test_web_and_agent_tools_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover web.py (DDG, SearXNG, Brave, Tavily, fetch) and agent.py subcommands."""
    # HTML parser & helpers
    md = html_to_markdown(
        "<html><head><title>Ignore</title></head><body>"
        "<script>var x=1;</script><h1>Title</h1><p>Hello   world</p>"
        "<ul><li>Item 1</li></ul></body></html>",
        max_chars=20,
    )
    assert "truncated" in md
    assert _unwrap_ddg_url("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com") == (
        "https://example.com"
    )
    assert _unwrap_ddg_url("https://example.com") == "https://example.com"
    assert _format_results([]) == "No search results found."

    def mock_http_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "searx" in url:
            return httpx.Response(
                200,
                json={"results": [{"title": "SearX", "url": "https://sx.org", "content": "Snip"}]},
            )
        if "brave.com" in url:
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"title": "Brave", "url": "https://br.org", "description": "BSnip"}
                        ]
                    }
                },
            )
        if "tavily.com" in url:
            return httpx.Response(
                200,
                json={
                    "results": [{"title": "Tavily", "url": "https://tv.org", "content": "TSnip"}]
                },
            )
        if "duckduckgo.com" in url:
            return httpx.Response(
                200,
                text=(
                    '<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fddg.org">'
                    "<b>DDG Title</b></a>"
                    '<a class="result__snippet">DDG Snippet</a>'
                ),
            )
        if "page.html" in url:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><h2>Heading</h2><p>Body text</p></body></html>",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="A" * 100,
        )

    orig_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(mock_http_handler)
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    from tether.tools.web import make_web_tool

    wspec = make_web_tool(max_fetch_chars=30)
    assert "Usage: web" in await wspec.invoke(["--help"])
    assert "Error: `--max`" in await wspec.invoke(["search", "--max", "bad", "ai"])
    assert "Error: missing `<query>`" in await wspec.invoke(["search"])
    assert "DDG Title" in await wspec.invoke(["search", "--max", "2", "ai"])

    monkeypatch.setenv("TAVILY_API_KEY", "tv_key")
    assert "Tavily" in await wspec.invoke(["search", "ai"])
    monkeypatch.setenv("BRAVE_API_KEY", "br_key")
    assert "Brave" in await wspec.invoke(["search", "ai"])
    monkeypatch.setenv("SEARXNG_URL", "https://searx.example.com")
    assert "SearX" in await wspec.invoke(["search", "ai"])

    assert "Error: missing `<url>`" in await wspec.invoke(["fetch"])
    assert "Error: URL must start" in await wspec.invoke(["fetch", "ftp://bad"])
    assert "## Heading" in await wspec.invoke(["fetch", "https://example.com/page.html"])
    assert "truncated" in await wspec.invoke(["fetch", "https://example.com/plain.txt"])
    assert "Error: unknown subcommand" in await wspec.invoke(["bogus"])

    # Agent tool edge cases
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    parent = store.create_session("Parent")
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir()
    (sk_dir / "researcher.md").write_text(
        "---\nname: researcher\nmodel: ollama/qwen3.5:9b\ntools: [web]\n---\nBody",
        encoding="utf-8",
    )
    loader = SkillLoader(search_dirs=[sk_dir])
    spawned: list[str] = []
    from tether.tools.agent import make_agent_tool

    aspec = make_agent_tool(
        store=store,
        parent_session_id=parent.id,
        default_model="ollama/qwen3.5:9b",
        parent_sandbox=SandboxPolicy(workspace_root=tmp_path),
        skill_loader=loader,
        worker_spawner=lambda sid: (spawned.append(sid), 123)[1],
        wait_timeout=0.1,
    )
    assert "Usage: agent" in await aspec.invoke(["--help"])
    assert "Error: missing `<goal>`" in await aspec.invoke(["spawn"])
    assert "Error: skill `nope` not found" in await aspec.invoke(
        ["spawn", "--skill", "nope", "goal"]
    )
    assert "No child sub-agent" in await aspec.invoke(["query", "--all", "test"])

    cid = await aspec.invoke(
        [
            "spawn",
            "--skill",
            "researcher",
            "--model",
            "ollama/gemma4:e4b",
            "--tools",
            "web,mem",
            "SubGoal",
        ]
    )
    assert cid in spawned
    # Also test spawn where skill provides model and tools
    cid2 = await aspec.invoke(["spawn", "--skill", "researcher", "SubGoal2"])
    assert cid2.startswith("ses_")

    assert "Error: missing `<session_id>`" in await aspec.invoke(["status"])
    assert "not found" in await aspec.invoke(["status", "ses_missing"])
    assert "[PENDING]" in await aspec.invoke(["status", cid])

    assert "Error: specify one or more" in await aspec.invoke(["wait"])
    # Wait timeout when child is still PENDING
    wait_out = await aspec.invoke(["wait", cid])
    assert cid in wait_out

    assert "Error: usage" in await aspec.invoke(["query"])
    assert "expects an integer" in await aspec.invoke(["query", cid, "q", "--top", "bad"])
    assert "Error: missing `<query>`" in await aspec.invoke(["query", cid])
    assert "No BM25 RAG chunks" in await aspec.invoke(["query", cid, "nothing_matches"])

    assert "Error: missing `<session_id>`" in await aspec.invoke(["read"])
    assert "not found" in await aspec.invoke(["read", "ses_missing"])
    assert cid in await aspec.invoke(["read", cid])
    assert "no final result yet" in await aspec.invoke(["read", cid, "--full"])

    assert "Error: missing `<session_id>`" in await aspec.invoke(["send"])
    assert "Error: missing `<message>`" in await aspec.invoke(["send", cid])
    assert "not found" in await aspec.invoke(["send", "ses_missing", "hi"])
    assert "resumed session" in await aspec.invoke(["send", cid, "follow up"])
    store.update_session(cid, status="RUNNING")
    assert "running session" in await aspec.invoke(["send", cid, "live msg"])
    assert "Error: unknown subcommand" in await aspec.invoke(["bogus"])


async def test_sandbox_store_and_harness_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover remaining branches in sandbox.py, store.py, harness.py, and cli.py."""
    import tether.sandbox as sb_mod

    # 1. _can_use_bwrap branches
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", None)
    monkeypatch.setattr(sb_mod.shutil, "which", lambda _: None)
    assert sb_mod._can_use_bwrap() is False
    assert sb_mod._can_use_bwrap() is False  # cached

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", None)
    monkeypatch.setattr(sb_mod.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setattr(
        sb_mod.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0),
    )
    assert sb_mod._can_use_bwrap() is True

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", None)

    def _raise_subproc(*a: Any, **kw: Any) -> Any:
        raise OSError("no bwrap")

    monkeypatch.setattr(sb_mod.subprocess, "run", _raise_subproc)
    assert sb_mod._can_use_bwrap() is False

    # SandboxPolicy validation & execution edge cases
    with pytest.raises(ValueError, match="Unsupported sandbox profile"):
        SandboxPolicy(profile="invalid")

    assert SandboxPolicy.from_dict(None).profile == "workspace-write"
    ro = SandboxPolicy(profile="read-only", workspace_root=tmp_path, use_kernel_sandbox=False)
    with pytest.raises(SandboxViolationError, match="Empty command"):
        ro.validate_bash_command("   ")
    with pytest.raises(SandboxViolationError, match="outside workspace"):
        ro.validate_bash_command("ls /etc/passwd")
    with pytest.raises(SandboxViolationError, match="mutating shell"):
        ro.validate_bash_command("echo hi > out.txt")
    with pytest.raises(SandboxViolationError, match="allowlist"):
        ro.validate_bash_command("python3 -c 'print(1)'")
    # Unclosed quote in validate_bash_command
    ro.validate_bash_command("echo 'unclosed")

    # _build_exec_argv with kernel sandbox forced True
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    ws_sb = SandboxPolicy(
        profile="workspace-write",
        workspace_root=tmp_path,
        use_kernel_sandbox=True,
        timeout_seconds=0.1,
        max_output_chars=40,
    )
    assert ws_sb._build_exec_argv("ls")[0] == "bwrap"
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", False)

    # execute_bash: stderr, exit code, empty output, truncation, timeout
    out_err = await ws_sb.execute_bash("echo err_msg >&2; exit 2")
    assert "[stderr]" in out_err and "[exit 2]" in out_err
    out_empty = await ws_sb.execute_bash("true")
    assert out_empty == "[exit 0]"
    out_trunc = await ws_sb.execute_bash("python3 -c 'print(\"X\" * 200)'")
    assert "truncated" in out_trunc
    out_timeout = await ws_sb.execute_bash("sleep 5")
    assert "timed out" in out_timeout

    # 2. store.py chunking & FTS edge cases
    from tether.store import _sanitize_fts_tokens, chunk_text

    assert chunk_text("") == []
    long_para = ("word " * 150) + "\n" + ("X" * 700) + "\n" + ("short line\n" * 40)
    chunks = chunk_text(f"# Heading 1\n\n{long_para}\n\n# Heading 2\n\nSmall block", max_chars=200)
    assert len(chunks) >= 4
    assert _sanitize_fts_tokens("the and or") == ["the", "and", "or"]

    store = SQLiteStore(db_path=tmp_path / "tether.db")
    s1 = store.create_session("Goal 1")
    store.update_session(s1.id, pid=999, tools=["web", "mem"])
    assert store.list_sessions(limit=5)[0].pid == 999
    store.index_text(s1.id, "observation", "obs_1", "Alpha beta gamma delta")
    assert store.search_chunks("   ", session_ids=[s1.id]) == []
    # Multi-token OR fallback + source_types filter
    hits = store.search_chunks(
        "Alpha nonexistent_token",
        session_ids=[s1.id],
        source_types=["observation"],
    )
    assert len(hits) == 1
    assert "not found" in store.get_session_digest("ses_nope")
    store.update_session(s1.id, result="R" * 200)
    assert "..." in store.get_session_digest(s1.id)

    # 3. harness.py & cli.py end-to-end integration
    monkeypatch.setattr(
        "tether.harness.subprocess.Popen",
        lambda *a, **kw: type("FakePopen", (), {"pid": 4242})(),
    )
    assert spawn_detached_worker(tmp_path / "tether.db", s1.id) == 4242

    # Harness init with skill name string, tools="web,mem", custom function
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir(exist_ok=True)
    (sk_dir / "helper.md").write_text(
        "---\nname: helper\nmodel: ollama/qwen3.5:9b\ntools: [web]\n---\nHelp instructions",
        encoding="utf-8",
    )

    def plain_fn(x: str) -> str:
        return x

    h = Harness(
        db_path=tmp_path / "tether.db",
        skill="helper",
        tools=[plain_fn, ToolSpec("t2", "d", plain_fn, [], False, False)],
        skill_search_dirs=[sk_dir],
    )
    h2 = Harness(db_path=tmp_path / "tether.db", tools="all")
    assert "web" in h2._enabled_tool_names

    # Test Harness spawn, send, and execute_session edge cases
    sid_spawned = h.spawn("Spawned goal")
    assert sid_spawned.startswith("ses_")

    with pytest.raises(ValueError, match="not found"):
        await h.send("ses_missing", "msg")
    with pytest.raises(ValueError, match="not found"):
        await h.execute_session("ses_missing")

    store.update_session(sid_spawned, status="RUNNING")
    assert (await h.send(sid_spawned, "while running")).status == "RUNNING"
    store.update_session(sid_spawned, status="COMPLETED")
    assert (await h.send(sid_spawned, "resume headless", headless=True)).status == "PENDING"

    # Execute session with: plain-text nudge -> late inbox on done -> final done
    step_idx = 0

    class ScriptedProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            nonlocal step_idx
            step_idx += 1
            if step_idx == 1:
                return ModelResponse(content="Thinking out loud without calling act")
            if step_idx == 2:
                # Enqueue a late inbox message while step 2 is running `done`
                store.enqueue_inbox(s_nudge.id, "Wait, add one more detail!")
                return ModelResponse(content="", action=ActionCall(cmd="done", stdin="First draft"))
            return ModelResponse(content="", action=ActionCall(cmd="done", stdin="Final draft"))

    register_provider("cli-mock", lambda name: ScriptedProvider())
    h_nudge = Harness(
        db_path=tmp_path / "tether.db",
        model="cli-mock/qwen",
        provider=ScriptedProvider(),
        max_steps=5,
    )
    s_nudge = h_nudge.create_session("Nudge & late inbox test")
    store.update_session(s_nudge.id, status="PENDING")
    # Also set skill on s_with_skill to cover execute_session loading skill from rec.skill
    s_with_skill = store.create_session("Skill session", model="cli-mock/qwen", skill="helper")
    step_idx = 0
    done_rec = await h_nudge.execute_session(s_nudge.id)
    assert done_rec.status == "COMPLETED" and done_rec.result == "Final draft"

    step_idx = 2
    await h_nudge.execute_session(s_with_skill.id)

    # Max steps reached without calling done
    class NeverDoneProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            return ModelResponse(content="Still thinking...")

    h_max = Harness(db_path=tmp_path / "tether.db", provider=NeverDoneProvider(), max_steps=2)
    s_max = await h_max.run("Never finishes")
    assert s_max.status == "FAILED" and "Max steps" in (s_max.result or "")

    # Provider raises unhandled exception
    class CrashProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            raise RuntimeError("provider exploded")

    h_crash = Harness(db_path=tmp_path / "tether.db", provider=CrashProvider(), max_steps=2)
    s_crash = await h_crash.run("Crash test")
    assert s_crash.status == "FAILED" and "provider exploded" in (s_crash.result or "")

    # 4. CLI full subcommand suite
    db_arg = str(tmp_path / "tether.db")
    step_idx = 2

    assert await _async_main([]) == 0
    assert (
        await _async_main(["--model", "cli-mock/qwen", "--db", db_arg, "Shorthand run goal"]) == 0
    )
    assert (
        await _async_main(
            ["run", "--headless", "--model", "cli-mock/qwen", "--db", db_arg, "Headless goal"]
        )
        == 0
    )

    assert await _async_main(["status", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["status", s_nudge.id, "--db", db_arg]) == 0

    assert await _async_main(["read", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["read", s_nudge.id, "--steps", "--db", db_arg]) == 0
    assert await _async_main(["read", s_nudge.id, "--digest", "--db", db_arg]) == 0
    assert await _async_main(["read", s_nudge.id, "--db", db_arg]) == 0

    assert await _async_main(["query", s_nudge.id, "Final", "--db", db_arg]) == 0
    assert await _async_main(["query", s_nudge.id, "nonexistent_xyz", "--db", db_arg]) == 0

    step_idx = 2
    assert await _async_main(["send", s_nudge.id, "--db", db_arg, "More work"]) == 0
    assert (
        await _async_main(["send", s_nudge.id, "--headless", "--db", db_arg, "Headless msg"]) == 0
    )

    step_idx = 2
    assert await _async_main(["_worker", s_nudge.id, "--db", db_arg]) == 0

    # Wait on a pending session that finishes after 1 poll
    s_wait = store.create_session("Wait session")

    async def _finish_soon() -> None:
        await asyncio.sleep(0.08)
        store.update_session(s_wait.id, status="COMPLETED", result="Done waiting")

    import asyncio

    task = asyncio.create_task(_finish_soon())
    assert await _async_main(["wait", s_wait.id, "--timeout", "1.0", "--db", db_arg]) == 0
    await task

    assert await _async_main(["list", "--db", db_arg]) == 0
    empty_db = str(tmp_path / "empty.db")
    assert await _async_main(["list", "--db", empty_db]) == 0


def test_cli_sync_main_entrypoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test synchronous main() entrypoint with explicit argv and sys.argv."""
    empty_db = str(tmp_path / "empty_sync.db")
    main(["list", "--db", empty_db])
    monkeypatch.setattr("sys.argv", ["tether", "list", "--db", empty_db])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0


async def test_remaining_100_percent_coverage_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover every remaining branch across the codebase for 100% coverage."""
    # 1. base.py AST fallback
    ast_mismatched1 = extract_fallback_action("""act(("done"), ("ast_pos_stdin"))""")
    assert ast_mismatched1 is not None and ast_mismatched1.stdin == "ast_pos_stdin"
    ast_mismatched2 = extract_fallback_action("""act(stdin="ast_kw_stdin", command='done')""")
    assert ast_mismatched2 is not None and ast_mismatched2.cmd == "done"

    # 2. multiplexer.py: register undecorated function & empty token list after split_cli
    mux = Multiplexer()
    mux.register(lambda a: a)
    res_quote_only = await mux.execute('"')
    assert res_quote_only.is_error and "empty command" in res_quote_only.output

    # 3. skills.py: skill load with custom_tools from tools.py
    sk_dir = tmp_path / "skills_cov" / "custom_sk"
    sk_dir.mkdir(parents=True)
    (sk_dir / "SKILL.md").write_text(
        "---\nname: custom_sk\ndescription: Custom\ntools: [web, custom-op]\n---\nUse custom-op.",
        encoding="utf-8",
    )
    (sk_dir / "tools.py").write_text(
        "from tether import tool\n"
        "@tool(name='custom-op')\n"
        "def custom_op() -> str:\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    loader = SkillLoader(search_dirs=[tmp_path / "skills_cov"])
    from tether.skills import make_skill_tool

    mux.register(make_skill_tool(loader, mux))
    out_sk = await mux.execute("skill load custom_sk")
    assert "[Skill `custom_sk` loaded]" in out_sk.output
    assert mux.get_tool("custom-op") is not None

    # 4. web.py: fetch short plain text (<= max_fetch_chars)
    orig_client = httpx.AsyncClient

    def short_plain_client(*a: Any, **kw: Any) -> httpx.AsyncClient:
        kw["transport"] = httpx.MockTransport(
            lambda req: httpx.Response(200, headers={"content-type": "text/plain"}, text="short_ok")
        )
        return orig_client(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", short_plain_client)
    from tether.tools.web import make_web_tool

    wspec = make_web_tool(max_fetch_chars=100)
    assert await wspec.invoke(["fetch", "https://example.com/short.txt"]) == "short_ok"

    # 5. agent.py: wait when child session is already COMPLETED (hits all_done break)
    store = SQLiteStore(db_path=tmp_path / "cov.db")
    p_rec = store.create_session("Parent")
    c_rec = store.create_session("Child", parent_id=p_rec.id)
    store.update_session(c_rec.id, status="COMPLETED", result="Child finished")
    from tether.tools.agent import make_agent_tool

    aspec = make_agent_tool(
        store=store,
        parent_session_id=p_rec.id,
        default_model="ollama/qwen3.5:9b",
        parent_sandbox=SandboxPolicy(workspace_root=tmp_path),
        skill_loader=loader,
        worker_spawner=lambda sid: 1,
    )
    wait_res = await aspec.invoke(["wait", c_rec.id])
    assert "COMPLETED" in wait_res

    # 6. store.py: chunk_text branches and search_chunks empty session_ids
    from tether.store import chunk_text

    text_with_empty_block = "# H1\n\n\n# H2\n\n" + ("A" * 50) + "\n\n" + ("B" * 50)
    chunks1 = chunk_text(text_with_empty_block, max_chars=70)
    assert len(chunks1) >= 2

    oversized_block = "short_first_line\n" + ("L" * 150)
    chunks2 = chunk_text(oversized_block, max_chars=50)
    assert any("short_first_line" in c for c in chunks2)

    assert store.search_chunks("anything", session_ids=[]) == []

    # 7. sandbox.py: ProcessLookupError when killing timed-out process
    import tether.sandbox as sb_mod

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", False)

    def _raise_proc_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(sb_mod.os, "killpg", _raise_proc_lookup)
    sb_timeout = SandboxPolicy(
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
        timeout_seconds=0.05,
    )
    res_to = await sb_timeout.execute_bash("python3 -c 'import time; time.sleep(0.12)'")
    assert "timed out" in res_to

    # 8. harness.py: execute_session loading custom_sk
    def dup_fn(x: str) -> str:
        return x

    class QuickDoneProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            return ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))

    h_cov = Harness(
        db_path=tmp_path / "cov.db",
        tools=[dup_fn, dup_fn],
        provider=QuickDoneProvider(),
        skill_search_dirs=[tmp_path / "skills_cov"],
    )
    s_sk = store.create_session("Run custom_sk", skill="custom_sk", tools=[])
    done_sk = await h_cov.execute_session(s_sk.id)
    assert done_sk.status == "COMPLETED"

    # 9. cli.py: fallback print_help when subcommand is unknown
    import tether.cli as cli_mod

    orig_build_parser = cli_mod.build_parser

    class DummyParser:
        def parse_args(self, argv: Any) -> Any:
            return type("NS", (), {"subcommand": "unknown"})()

        def print_help(self) -> None:
            pass

    monkeypatch.setattr(cli_mod, "build_parser", lambda: DummyParser())
    assert await _async_main(["run"]) == 0
    monkeypatch.setattr(cli_mod, "build_parser", orig_build_parser)
