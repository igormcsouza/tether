"""Sandboxed shell execution tool (`bash`)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import ApprovalNeeded, SandboxPolicy

# `<tests> 2>&1 | head -N` cuts the runner's summary (it prints last) and hides its exit code.
_HEAD_PIPE = re.compile(r"(?P<cmd>.+?)\s*\|\s*head(?:\s+-n)?(?:\s+-?(?P<n>\d+))?\s*", re.DOTALL)
HEAD_TAIL_LINES = 6
# `cd /testbed && <cmd>`: models assume a container path, but the shell starts in the workspace
_CD_PREFIX = re.compile(r"cd\s+(?P<dir>\S+)\s*(?:&&|;)\s*(?P<rest>.+)", re.DOTALL)


def _missing_cd(cmd: str, root: Path) -> tuple[str, str] | None:
    """(dir, rest) of `cd <dir> && <rest>` when <dir> does not exist, else None (#79)."""
    m = _CD_PREFIX.fullmatch(cmd)
    if not m:
        return None
    path = root / m["dir"].strip("'\"")  # an absolute dir replaces root
    return None if path.is_dir() else (m["dir"], m["rest"])


def _test_head(cmd: str) -> tuple[str, int] | None:
    """The test command and N of `<test runner> | head -N`, else None (#173)."""
    from tether.harness import is_test_cmd  # lazy: the harness imports the tools

    m = _HEAD_PIPE.fullmatch(cmd)
    if not m or "|" in m["cmd"] or not is_test_cmd(m["cmd"]):
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


TIMEOUT_PREFIX = "Error: command timed out"
# A timed-out `server &` looks like a hang; the model repeated it 16 times without this (#319).
BACKGROUND_HINT = (
    "A background job (`&`) keeps the command open. Instead: run it in the foreground with "
    "`timeout N <cmd>`, or send its output away: `<cmd> >/dev/null 2>&1 &`."
)
TIMEOUT_HINT = (
    "Instead: run a shorter command, or start a long job in the background with a timeout."
)


def _has_background_job(script: str) -> bool:
    """True when an unquoted `&` backgrounds a job; `&&`, `&>`, `>&` and escaped `&` do not."""
    quote = ""
    i = 0
    while i < len(script):
        c = script[i]
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"':
                i += 1
        elif c == "\\":
            i += 1
        elif c in "'\"":
            quote = c
        elif c == "&":
            if script[i + 1 : i + 2] == "&":
                i += 2
                continue
            before = script[i - 1 : i] if i else ""
            if script[i + 1 : i + 2] != ">" and before != ">":
                return True
        i += 1
    return False


def make_bash_tool(
    sandbox: SandboxPolicy, on_approval: Callable[[ApprovalNeeded], None] | None = None
) -> ToolSpec:
    # on_approval lets the harness pause the session (#59); without it the request is a refusal.
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
        note = ""
        if cd := _missing_cd(cmd_str, Path(sandbox.workspace_root)):
            # qwen3.5:9b lost a step to `cd /testbed && ...` in 3 of 6 paasio runs
            cmd_str = cd[1]
            note = f"[`cd {cd[0]}` skipped: no such directory; commands run in the workspace]\n"
        try:
            if stdin is None and (head := _test_head(cmd_str)):
                out = _keep_summary(await sandbox.execute_bash(head[0]), head[1])
            else:
                out = await sandbox.execute_bash(cmd_str, stdin=stdin)
        except ApprovalNeeded as exc:
            if on_approval is None:
                raise
            on_approval(exc)
            return str(exc)
        if out.startswith(TIMEOUT_PREFIX):
            bg = _has_background_job(cmd_str if stdin is None else stdin)
            out = f"{out.rstrip()}\n{BACKGROUND_HINT if bg else TIMEOUT_HINT}"
        return note + out

    return build_tool_spec(
        _bash,
        name="bash",
        description="Execute sandboxed shell commands",
        custom_help=help_str,
        raw_dispatch=True,
    )
