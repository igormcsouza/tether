"""Workspace-jailed file viewing and stdin patching tool (`edit`)."""

from __future__ import annotations

import ast
import difflib
import re

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxPolicy

_BLOCK_RE = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n?>>>>>>> REPLACE", re.DOTALL)


def _apply_blocks(text: str, stdin: str) -> str | tuple[str, int]:
    """Apply SEARCH/REPLACE blocks atomically; each SEARCH must match exactly once."""
    blocks = _BLOCK_RE.findall(stdin)
    if not blocks:
        return "no complete `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` block in stdin."
    for i, (old, new) in enumerate(blocks, 1):
        n = text.count(old)
        if n != 1:
            how = "not found (exact text, incl. indentation)" if n == 0 else f"matches {n} times"
            return (
                f"SEARCH block {i} {how}; nothing changed. First line: `{old.splitlines()[0][:60]}`"
            )
        text = text.replace(old, new, 1)
    return text, len(blocks)


def _syntax_warning(path: str, old: str | None, new: str) -> str:
    """Tell the model when its edit broke a previously valid .py file (bad indentation, etc.)."""
    if not path.endswith(".py"):
        return ""
    try:
        ast.parse(new)
        return ""
    except SyntaxError as exc:
        try:
            ast.parse(old or "")
        except SyntaxError:
            return ""  # already broken before this edit
        return f" WARNING: `{path}` no longer parses: {exc.msg} at line {exc.lineno}. Fix it now."


def _parse_line_range(spec: str, total_lines: int) -> tuple[int, int] | str:
    if ":" not in spec:
        try:
            n = int(spec)
            return max(1, n), min(total_lines, n)
        except ValueError:
            return f"invalid line range `{spec}` (expected `start:end`)."
    left, right = spec.split(":", 1)
    try:
        start = int(left) if left else 1
        end = int(right) if right else total_lines
    except ValueError:
        return f"invalid line range `{spec}` (expected integers `start:end`)."
    start = max(1, start)
    end = min(max(start, end), max(1, total_lines))
    return start, end


def make_edit_tool(sandbox: SandboxPolicy) -> ToolSpec:
    help_str = (
        "Usage: edit view <path> [--lines a:b] | edit write <path> [stdin] | "
        "edit replace <path> --lines a:b [stdin]\n"
        "Desc : View, write file, or replace lines. Or stdin `<<<<<<< SEARCH`/`=======`/"
        "`>>>>>>> REPLACE` blocks (exact text; no --lines)."
    )

    def _edit(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str

        sub = args[0]
        if sub == "view":
            if len(args) < 2:
                return f"Error: missing `<path>`.\n{help_str}"
            target = sandbox.resolve_safe_path(args[1], write=False)
            if not target.is_file():
                return f"Error: file `{args[1]}` not found."
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            start, end = 1, min(len(lines), 100)
            if "--lines" in args:
                idx = args.index("--lines")
                if idx + 1 >= len(args):
                    return f"Error: `--lines` requires `start:end`.\n{help_str}"
                rng = _parse_line_range(args[idx + 1], len(lines))
                if isinstance(rng, str):
                    return f"Error: {rng}"
                start, end = rng
            numbered = [f"{i:4d}: {lines[i - 1]}" for i in range(start, end + 1)]
            header = f"[{args[1]} lines {start}-{end} of {len(lines)}]"
            return "\n".join([header, *numbered])

        if sub == "write":
            if len(args) < 2:
                return f"Error: missing `<path>`.\n{help_str}"
            if stdin is None:
                return f"Error: `edit write` requires file content in `stdin`.\n{help_str}"
            target = sandbox.resolve_safe_path(args[1], write=True)
            old_text = (
                target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(stdin, encoding="utf-8")
            if old_text is None:
                line_cnt = len(stdin.splitlines())
                return f"Wrote {len(stdin):,} chars ({line_cnt} lines) to `{args[1]}`."
            old_lines = old_text.splitlines()
            new_lines = stdin.splitlines()
            ops = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes()
            removed = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag != "equal")
            added = sum(j2 - j1 for tag, _, _, j1, j2 in ops if tag != "equal")
            first = next(
                (old_lines[i1] for tag, i1, i2, _, _ in ops if tag != "equal" and i2 > i1),
                "none",
            )
            n_old, n_new = len(old_lines), len(new_lines)
            tail = f"{removed} removed, {added} added; first removed: {str(first).strip()[:60]}"
            if removed == added == 0 and old_text != stdin:
                tail = "only whitespace/newline changes"
            summary = f"Replaced {n_old} line{'s' * (n_old != 1)} with {n_new} ({tail})"
            if len(new_lines) < len(old_lines):
                summary += (
                    " File shrank; for partial changes use `edit replace <path> --lines a:b`."
                )
            return summary + _syntax_warning(args[1], old_text, stdin)

        if sub == "replace":
            if len(args) >= 2 and "--lines" not in args and stdin and "<<<<<<< SEARCH" in stdin:
                target = sandbox.resolve_safe_path(args[1], write=True)
                if not target.is_file():
                    return f"Error: file `{args[1]}` not found."
                old_text = target.read_text(encoding="utf-8", errors="replace")
                res = _apply_blocks(old_text, stdin)
                if isinstance(res, str):
                    return f"Error: {res}"
                target.write_text(res[0], encoding="utf-8")
                return f"Replaced {res[1]} block(s) in `{args[1]}`." + _syntax_warning(
                    args[1], old_text, res[0]
                )
            if len(args) < 2 or "--lines" not in args:
                return (
                    f"Error: `edit replace` requires `<path> --lines start:end` "
                    f"and `stdin`.\n{help_str}"
                )
            if stdin is None:
                return f"Error: `edit replace` requires replacement block in `stdin`.\n{help_str}"
            target = sandbox.resolve_safe_path(args[1], write=True)
            if not target.is_file():
                return f"Error: file `{args[1]}` not found."
            idx = args.index("--lines")
            if idx + 1 >= len(args):
                return f"Error: `--lines` requires `start:end`.\n{help_str}"
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            rng = _parse_line_range(args[idx + 1], len(lines))
            if isinstance(rng, str):
                return f"Error: {rng}"
            start, end = rng
            replacement_lines = stdin.splitlines()
            updated = lines[: start - 1] + replacement_lines + lines[end:]
            new_text = "\n".join(updated) + ("\n" if stdin.endswith("\n") or lines else "")
            old_text = "\n".join(lines)
            target.write_text(new_text, encoding="utf-8")
            return (
                f"Replaced lines {start}:{end} in `{args[1]}` with {len(replacement_lines)} lines."
                + _syntax_warning(args[1], old_text, new_text)
            )

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _edit,
        name="edit",
        description="View, create, or patch workspace files via stdin",
        custom_help=help_str,
        raw_dispatch=True,
    )
