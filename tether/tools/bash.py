"""Sandboxed shell execution tool (`bash`)."""

from __future__ import annotations

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxPolicy


def make_bash_tool(sandbox: SandboxPolicy) -> ToolSpec:
    help_str = (
        "Usage: bash <command> (or pass script via stdin)\n"
        "Desc : Run shell command inside workspace sandbox."
    )

    async def _bash(args: list[str], stdin: str | None = None) -> str:
        if args and args[0] in ("--help", "-h"):
            return help_str
        cmd_str = " ".join(args).strip()
        if not cmd_str and not stdin:
            return f"Error: missing `<command>`.\n{help_str}"
        return await sandbox.execute_bash(cmd_str, stdin=stdin)

    return build_tool_spec(
        _bash,
        name="bash",
        description="Execute sandboxed shell commands",
        custom_help=help_str,
        raw_dispatch=True,
    )
