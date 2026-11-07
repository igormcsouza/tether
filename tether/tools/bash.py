"""Sandboxed shell execution tool (`bash`)."""

from __future__ import annotations

import re

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxPolicy

# `<tests> 2>&1 | head -N` cuts the runner's summary (it prints last) and hides its exit code.
_HEAD_PIPE = re.compile(r"(?P<cmd>.+?)\s*\|\s*head(?:\s+-n)?(?:\s+-?(?P<n>\d+))?\s*", re.DOTALL)
HEAD_TAIL_LINES = 6


def _test_head(cmd: str) -> tuple[str, int] | None:
    """The test command and N of `<test runner> | head -N`, else None (#173)."""
    from tether.harness import _TEST_CMD  # lazy: the harness imports the tools

    m = _HEAD_PIPE.fullmatch(cmd)
    if not m or "|" in m["cmd"] or not _TEST_CMD.search(m["cmd"]):
        return None
    return m["cmd"], int(m["n"] or 10)


def _keep_summary(out: str, n: int) -> str:
    """`head -n` of `out`, plus its last lines (summary, `[exit N]`) when more was cut."""
    lines = out.splitlines()
    if len(lines) <= n + HEAD_TAIL_LINES:
        return out
    cut = len(lines) - n - HEAD_TAIL_LINES
    marker = f"[... {cut} lines cut by `head`; the end of the output:]"
    return "\n".join([*lines[:n], marker, *lines[-HEAD_TAIL_LINES:]])


def make_bash_tool(sandbox: SandboxPolicy) -> ToolSpec:
    help_str = (
        "Usage: bash <command> (or pass script via stdin)\n"
        "Desc : Run shell command inside workspace sandbox."
    )

    async def _bash(args: list[str], stdin: str | None = None) -> str:
        if args and args[0] in ("--help", "-h"):
            return help_str
        # The multiplexer passes the raw command text as a single arg so quotes survive.
        cmd_str = " ".join(args).strip()
        if not cmd_str and not stdin:
            return f"Error: missing `<command>`.\n{help_str}"
        if stdin is None and (head := _test_head(cmd_str)):
            return _keep_summary(await sandbox.execute_bash(head[0]), head[1])
        return await sandbox.execute_bash(cmd_str, stdin=stdin)

    return build_tool_spec(
        _bash,
        name="bash",
        description="Execute sandboxed shell commands",
        custom_help=help_str,
        raw_dispatch=True,
    )
