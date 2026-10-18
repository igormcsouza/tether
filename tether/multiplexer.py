"""Virtual CLI Multiplexer (`act(cmd, stdin)`) with 9B quirk normalization and JIT --help."""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxViolationError

_SYNTAX_ERROR_MARKERS = (
    "\nUsage:",
    "expects an integer",
    "invalid line range",
    "URL must start with",
)


@dataclass(slots=True)
class DispatchResult:
    output: str
    is_done: bool = False
    is_waiting_input: bool = False
    final_result: str | None = None
    is_error: bool = False
    error_kind: str | None = None


def _classify_tool_error(output: str) -> str:
    """Classify a tool Error: response as syntax_error (JIT --help / bad args) vs runtime_error."""
    if any(marker in output for marker in _SYNTAX_ERROR_MARKERS):
        return "syntax_error"
    return "runtime_error"


def normalize_cmd(raw_cmd: str) -> str:
    """Normalize common small-model CLI syntax quirks deterministically."""
    s = raw_cmd.strip()
    # Strip wrapping markdown code fences or inline backticks
    if s.startswith("```") and s.endswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            s = "\n".join(lines[1:-1]).strip()
    if len(s) >= 2 and s.startswith("`") and s.endswith("`") and "`" not in s[1:-1]:
        s = s[1:-1].strip()
    # Strip leading shell prompt markers ($ or >)
    if s.startswith("$ "):
        s = s[2:].strip()
    elif s.startswith("> "):
        s = s[2:].strip()
    # Strip redundant leading `tether ` prefix if the model typed `tether web search ...`
    if s.startswith("tether "):
        s = s[len("tether ") :].strip()
    return s


def unescape_literal_newlines(stdin: str | None) -> str | None:
    """Unescape literal `\\n`/`\\t` when a small model sent a whole payload on one line."""
    if stdin and "\n" not in stdin and "\\n" in stdin:
        return stdin.replace("\\n", "\n").replace("\\t", "\t")
    return stdin


def split_cli(cmd: str) -> list[str]:
    """Split a CLI command string using POSIX shlex with graceful fallback on unclosed quotes."""
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return [tok.strip("\"'") for tok in cmd.split() if tok.strip("\"'")]


class Multiplexer:
    """Routes `act(cmd, stdin)` invocations across registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, item: ToolSpec | Callable[..., Any]) -> ToolSpec:
        if isinstance(item, ToolSpec):
            spec = item
        elif hasattr(item, "__tether_tool__"):
            spec = item.__tether_tool__
        else:
            spec = build_tool_spec(item)
        self._tools[spec.name] = spec
        return spec

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def toolbox_index(self) -> str:
        """Render the ultra-compact 1-line-per-tool directory for the system prompt."""
        lines = [spec.index_line() for spec in self._tools.values()]
        return "\n".join(lines)

    async def execute(self, cmd: str, stdin: str | None = None) -> DispatchResult:
        """Execute a virtual CLI command and return a DispatchResult."""
        clean_cmd = normalize_cmd(cmd)
        if not clean_cmd:
            avail = ", ".join(self._tools.keys())
            return DispatchResult(
                output=f"Error: empty command. Available tools: {avail}. Run `<tool> --help`.",
                is_error=True,
                error_kind="syntax_error",
            )

        tokens = split_cli(clean_cmd)
        if not tokens:
            return DispatchResult(
                output="Error: empty command.",
                is_error=True,
                error_kind="syntax_error",
            )

        name = tokens[0]
        args = tokens[1:]

        if name in ("help", "--help", "-h"):
            if args and args[0] in self._tools:
                return DispatchResult(output=self._tools[args[0]].help_text())
            return DispatchResult(
                output=f"Available commands:\n{self.toolbox_index()}\nRun `<cmd> --help` for usage."
            )

        spec = self._tools.get(name)
        if spec is None:
            avail = ", ".join(self._tools.keys())
            hint = f" For shell commands use `bash {clean_cmd}`." if "bash" in self._tools else ""
            return DispatchResult(
                output=f"Error: unknown command `{name}`. Enabled tools: {avail}.{hint}",
                is_error=True,
                error_kind="unknown_cmd",
            )

        if name == "bash":
            # shlex already stripped quotes; hand the shell the original text (#37).
            args = clean_cmd.split(None, 1)[1:]

        if name == "done" or (name == "edit" and args[:1] in (["write"], ["replace"])):
            stdin = unescape_literal_newlines(stdin)

        try:
            out = await spec.invoke(args, stdin=stdin)
        except SandboxViolationError as exc:
            return DispatchResult(output=str(exc), is_error=True, error_kind="runtime_error")
        except Exception as exc:
            return DispatchResult(
                output=f"Error executing `{name}`: {exc}\n{spec.help_text()}",
                is_error=True,
                error_kind="runtime_error",
            )

        if name == "done" and not out.startswith("Error:") and not out.startswith("Usage:"):
            if "--ask" in args:
                return DispatchResult(output=out, is_waiting_input=True, final_result=out)
            return DispatchResult(output=out, is_done=True, final_result=out)

        is_err = out.startswith("Error:")
        return DispatchResult(
            output=out,
            is_error=is_err,
            error_kind=_classify_tool_error(out) if is_err else None,
        )
