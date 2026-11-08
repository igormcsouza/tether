"""Session export as a Markdown transcript."""

from __future__ import annotations

import re

from tether.store import SQLiteStore

MAX_TOOL_CHARS = 2000


def _fence(text: str) -> str:
    """Return a run of backticks one longer than the longest run in text, at least 3."""
    n = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, n + 1)


def to_markdown(store: SQLiteStore, session_id: str) -> str:
    """Return the session `session_id` as a Markdown transcript."""
    rec = store.get_session(session_id)
    if rec is None:
        raise KeyError(session_id)
    lines = [
        f"# Session {session_id}",
        "",
        f"- Goal: {rec.goal}",
        f"- Model: {rec.model}",
        f"- Status: {rec.status}",
        f"- Steps: {rec.step_count}",
        "",
    ]
    for turn in store.get_turns(session_id):
        if turn.role == "assistant" and turn.tool_cmd:
            lines += [f"## Step {turn.step}", "", f"`{turn.tool_cmd}`", ""]
            if turn.tool_stdin:
                f = _fence(turn.tool_stdin)
                lines += [f + "text", turn.tool_stdin, f, ""]
        elif turn.role == "tool":
            content = turn.content
            cut = len(content) - MAX_TOOL_CHARS
            f = _fence(content)
            lines += [f + "text", content[:MAX_TOOL_CHARS], f]
            if cut > 0:
                lines.append(f"[... {cut} chars cut]")
            lines.append("")
    lines += ["## Result", "", rec.result or ""]
    return "\n".join(lines) + "\n"
