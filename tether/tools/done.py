"""Mandatory explicit task completion tool (`done`)."""

from __future__ import annotations

from tether.decorator import ToolSpec, build_tool_spec


def make_done_tool() -> ToolSpec:
    help_str = (
        "Usage: done [--ask] [answer] (or pass multiline report/question via stdin)\n"
        "Desc : Complete the task, or pass --ask to pause and request input."
    )

    def _done(args: list[str], stdin: str | None = None) -> str:
        if args and args[0] in ("--help", "-h"):
            return help_str
        clean_args = [a for a in args if a != "--ask"]
        body_parts: list[str] = []
        if clean_args:
            body_parts.append(" ".join(clean_args).strip())
        if stdin and stdin.strip():
            body_parts.append(stdin.strip())
        final_text = "\n\n".join(body_parts).strip()
        if not final_text:
            return (
                f"Error: provide final deliverable or question via `stdin` or argument.\n{help_str}"
            )
        return final_text

    return build_tool_spec(
        _done,
        name="done",
        description="Complete task and submit final deliverable",
        custom_help=help_str,
        raw_dispatch=True,
    )
