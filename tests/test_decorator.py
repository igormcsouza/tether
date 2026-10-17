"""Unit tests for tether/decorator.py (@tool introspection, CLI argument parsing, JIT --help)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from tether import Harness, SandboxPolicy, tool
from tether.decorator import ParamSpec, ToolSpec, build_tool_spec
from tether.multiplexer import Multiplexer


async def test_custom_tool_introspection_and_9b_quirks(tmp_path: Path) -> None:
    """Test @tool CLI parsing, stdin payloads, 9B quirk normalization, and JIT --help on errors."""

    @tool(name="crm", description="Update customer subscription tier")
    def update_tier(
        customer_id: int,
        tier: Literal["free", "pro", "enterprise"] = "pro",
        stdin: str | None = None,
    ) -> str:
        """Update customer tier with optional audit note via stdin."""
        return f"customer={customer_id} tier={tier} note={stdin or 'none'}"

    harness = Harness(db_path=tmp_path / "tether.db", tools=[update_tier])
    mux = harness.build_multiplexer(
        session_id="ses_1",
        enabled_tools=["crm"],
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model="ollama/qwen3.5:9b",
    )

    help_res = await mux.execute("crm --help")
    assert "Usage: crm <customer_id:int>" in help_res.output
    assert "free|pro|enterprise" in help_res.output

    err_res = await mux.execute("crm not_an_int")
    assert err_res.is_error
    assert "expects int" in err_res.output
    assert "Usage: crm" in err_res.output

    ok_res = await mux.execute("`$ crm 1042 --tier enterprise`", stdin="Approved by finance")
    assert not ok_res.is_error
    assert ok_res.output == "customer=1042 tier=enterprise note=Approved by finance"


async def test_decorator_parameter_types_and_edge_cases() -> None:
    """Cover Literal, int, float, bool, variadic, async, stdin fallback, and coercion errors."""

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

    @tool(name="async-echo")
    async def async_echo(msg: str) -> str:
        return f"async:{msg}"

    mux.register(async_echo)
    assert (await mux.execute("async-echo hello")).output == "async:hello"

    long_spec = build_tool_spec(lambda x: x, name="long-tool", description="A" * 60)
    assert long_spec.index_line().endswith("...")

    def broken_hints(x: NonExistentType) -> str:  # type: ignore[name-defined] # noqa: F821
        return x

    bh_spec = build_tool_spec(broken_hints)
    assert bh_spec.params[0].type_name == "str"

    @tool(name="single-str")
    def single_str(payload: str) -> str:
        return f"got:{payload}"

    mux.register(single_str)
    r_stdin = await mux.execute("single-str", stdin="hello_stdin")
    assert r_stdin.output == "got:hello_stdin"
    assert "missing required argument" in (await mux.execute("single-str")).output

    @tool(name="greet")
    def greet(name: str) -> str:
        return f"hi {name}"

    mux.register(greet)
    r_greet = await mux.execute("greet Alice Bob Carol")
    assert r_greet.output == "hi Alice Bob Carol"

    @tool(name="add-int")
    def add_int(x: int) -> str:
        return str(x)

    mux.register(add_int)
    r_unexpected = await mux.execute("add-int 1 2 3")
    assert "Error: unexpected positional arguments" in r_unexpected.output

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
