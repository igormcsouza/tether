"""Virtual CLI Multiplexer (`act(cmd, stdin)`) with 9B quirk normalization and JIT --help."""

from __future__ import annotations

import re
import shlex
import shutil
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
    return _unwrap_shell(s)


_SHELL_WRAP_RE = re.compile(
    r"(?:(?:/bin/)?(?:ba)?sh\s+)?-[a-z]*c\s+(?:(?P<q>['\"])(?P<body>.*)(?P=q)|(?P<raw>\S.*))",
    re.DOTALL,
)
_DQ_ESCAPES = re.compile(r'\\(["$`\\])')


def _unwrap_shell(s: str) -> str:
    """`bash -lc 'ls'` / `sh -c "ls"` -> `bash ls` (models trained on shell tools wrap commands)."""
    m = _SHELL_WRAP_RE.fullmatch(s)
    if not m:
        return s
    body = m.group("raw") or m.group("body")
    if m.group("q") == '"':
        body = _DQ_ESCAPES.sub(r"\1", body)
    return f"bash {body}"


_SHELL_BUILTINS = frozenset(
    "cd echo export set unset source test type read printf pwd exit true false alias wait".split()
)


def _looks_like_shell(word: str) -> bool:
    """True for a program on PATH, a shell builtin, a path or `VAR=value`; typos stay unknown."""
    return bool(shutil.which(word)) or word in _SHELL_BUILTINS or "/" in word or "=" in word


_APPLY_PATCH_RE = re.compile(
    r"(?:^|\n)\s*(?:bash\s+)?apply_patch\b[^\n]*\n(?P<patch>\s*\*\*\* Begin Patch.*)", re.DOTALL
)
_HEREDOC_RE = re.compile(r"[ \t]*<<-?[ \t]*(['\"]?)(\w+)\1[ \t]*\n(.*?)\n?\2[ \t]*$", re.DOTALL)


def split_heredoc(cmd: str) -> tuple[str, str | None]:
    """Split a trailing shell heredoc off `cmd` into stdin (models write `edit ... <<'EOF'`)."""
    m = _HEREDOC_RE.search(cmd)
    return (cmd[: m.start()].strip(), m.group(3)) if m else (cmd, None)


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

        patch = _APPLY_PATCH_RE.search(f"{clean_cmd}\n{stdin or ''}")
        if patch and "edit" in self._tools:  # patch text may sit in cmd, or in stdin of `bash`
            clean_cmd, stdin = "apply_patch", patch.group("patch")
        if stdin is None and not clean_cmd.startswith("bash"):
            clean_cmd, stdin = split_heredoc(clean_cmd)
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

        if name == "apply_patch" and "edit" in self._tools:  # Codex-family models' native verb
            clean_cmd, name = f"edit {clean_cmd}", "edit"
            args = tokens
        spec = self._tools.get(name)
        if spec is None and "bash" in self._tools:
            from tether.tools import ALL_BUILTIN_TOOLS  # lazy: tools import this module

            if name not in ALL_BUILTIN_TOOLS and _looks_like_shell(name):
                # A bare shell command (`ls -la`): the sandboxed bash tool runs it, no retry step.
                name, spec = "bash", self._tools["bash"]
                clean_cmd = f"bash {clean_cmd}"
        if spec is None:
            avail = ", ".join(self._tools.keys())
            hint = f" For shell commands use `bash {clean_cmd}`." if "bash" in self._tools else ""
            from tether.tools import ALL_BUILTIN_TOOLS  # lazy: tools import this module

            head = (
                f"`{name}` is disabled"
                if name in ALL_BUILTIN_TOOLS
                else f"unknown command `{name}`"
            )
            enable = "Enable more: --tools bash,edit (CLI), tools=[...] (SDK), `tools:` (skill)."
            return DispatchResult(
                output=f"Error: {head}. Enabled tools: {avail}. {enable}{hint}",
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
