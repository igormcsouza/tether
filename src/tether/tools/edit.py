"""Workspace-jailed file viewing and stdin patching tool (`edit`)."""

from __future__ import annotations

from tether.decorator import ToolSpec, build_tool_spec
from tether.sandbox import SandboxPolicy


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
        "Desc : View numbered lines, write file from stdin, or replace line range."
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
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(stdin, encoding="utf-8")
            line_cnt = len(stdin.splitlines())
            return f"Wrote {len(stdin):,} chars ({line_cnt} lines) to `{args[1]}`."

        if sub == "replace":
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
            target.write_text(
                "\n".join(updated) + ("\n" if stdin.endswith("\n") or lines else ""),
                encoding="utf-8",
            )
            return (
                f"Replaced lines {start}:{end} in `{args[1]}` with {len(replacement_lines)} lines."
            )

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _edit,
        name="edit",
        description="View, create, or patch workspace files via stdin",
        custom_help=help_str,
        raw_dispatch=True,
    )
