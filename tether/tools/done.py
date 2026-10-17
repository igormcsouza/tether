"""Mandatory explicit task completion tool (`done`)."""

from __future__ import annotations

from tether.decorator import ToolSpec, build_tool_spec


def make_done_tool() -> ToolSpec:
    help_str = (
        "Usage: done [answer] (or pass multiline report via stdin)\n"
        "Desc : Complete the task and submit final deliverable."
    )

    def _done(args: list[str], stdin: str | None = None) -> str:
        if args and args[0] in ("--help", "-h"):
            return help_str
        body_parts: list[str] = []
        if args:
            body_parts.append(" ".join(args).strip())
        if stdin and stdin.strip():
            body_parts.append(stdin.strip())
        final_text = "\n\n".join(body_parts).strip()
        if not final_text:
            return f"Error: provide final deliverable via `stdin` or argument.\n{help_str}"
        return final_text

    return build_tool_spec(
        _done,
        name="done",
        description="Complete task and submit final deliverable",
        custom_help=help_str,
        raw_dispatch=True,
    )
