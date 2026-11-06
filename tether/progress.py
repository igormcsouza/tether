"""Live progress on stderr for a foreground `tether run`: activity dots and `--verbose`."""

from __future__ import annotations

import asyncio
import sys
from typing import TextIO

from tether.store import SQLiteStore, TurnRecord


def step_line(turn: TurnRecord) -> str | None:
    """Format a single assistant turn with a tool command as a progress line."""
    if turn.role != "assistant" or not turn.tool_cmd:
        return None

    cmd = turn.tool_cmd.replace("\n", " ")
    if len(cmd) > 80:
        cmd = cmd[:77] + "..."

    total_tokens = turn.prompt_tokens + turn.completion_tokens
    duration_s = turn.duration_ms / 1000.0

    return f"[step {turn.step}] {cmd} ({duration_s:.1f}s, {total_tokens} tok)"


def dots_label(model: str, turns: list[TurnRecord]) -> str:
    """Generate the label for the animated dots."""
    # Find the last assistant turn with a tool_cmd
    last_assistant_call: TurnRecord | None = None
    for turn in turns:
        if turn.role == "assistant" and turn.tool_cmd:
            last_assistant_call = turn

    if last_assistant_call is None:
        return f"waiting for {model}"

    cmd = (last_assistant_call.tool_cmd or "").replace("\n", " ")
    if len(cmd) > 40:
        cmd = cmd[:37] + "..."

    return f"step {last_assistant_call.step} · {cmd}"


async def watch(
    store: SQLiteStore,
    session_id: str,
    model: str,
    *,
    verbose: bool,
    tty: bool,
    stream: TextIO | None = None,
    interval: float = 0.4,
) -> None:
    """Draw activity dots (tty) and/or one line per step (verbose) on `stream` until cancelled."""
    stream = stream or sys.stderr
    seen: set[int] = set()

    def lines() -> list[TurnRecord]:
        turns = store.get_turns(session_id)
        if verbose:
            for turn in turns:
                if turn.id not in seen and (line := step_line(turn)):
                    stream.write(("\r\033[K" if tty else "") + line + "\n")
                seen.add(turn.id)
        return turns

    tick = 0
    try:
        while True:
            turns = lines()
            if tty:
                tick += 1
                stream.write(f"\r\033[K{dots_label(model, turns)} {'.' * (tick % 3 + 1)}")
            stream.flush()
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        lines()
        if tty:
            stream.write("\r\033[K")
        stream.flush()
