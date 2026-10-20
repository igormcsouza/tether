"""State Plane: ContextAssembler, Ephemeral Observation Folding, and Token Estimator."""

from __future__ import annotations

import json
import shlex
from typing import Any

from tether.store import ObservationRecord, TurnRecord

ACT_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "act",
        "description": "Run a CLI command from the toolbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "CLI command or `<cmd> --help`"},
                "stdin": {"type": "string", "description": "Optional multiline input"},
            },
            "required": ["cmd"],
        },
    },
}


STDIN_REPLAY_CHARS = 400


def estimate_tokens(text: str) -> int:
    """Fast deterministic token approximation (~4 chars per token)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
) -> int:
    """Estimate total tokens across messages and tool schema payload."""
    total = 0
    for msg in messages:
        total += 4  # framing overhead per message
        total += estimate_tokens(str(msg.get("content") or ""))
        if msg.get("tool_calls"):
            total += estimate_tokens(json.dumps(msg["tool_calls"]))
    if tools:
        total += estimate_tokens(json.dumps(tools))
    return total


def elide_active_observation(
    obs_id: str, raw_output: str, max_chars: int = 2400, mem_enabled: bool = True
) -> str:
    """Slice oversized active observations into Head + Tail in L1."""
    if len(raw_output) <= max_chars:
        return f"[{obs_id}] {raw_output}"
    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len
    elided_count = len(raw_output) - (head_len + tail_len)
    head = raw_output[:head_len].rstrip()
    tail = raw_output[-tail_len:].lstrip()
    recall_hint = (
        f"use `mem search <query>` or `mem recall {obs_id}`"
        if mem_enabled
        else "re-run the command for the full output"
    )
    marker = f"\n... [{obs_id}: {elided_count:,} middle chars elided in L1 | {recall_hint}] ...\n"
    return f"[{obs_id}] {head}{marker}{tail}"


def _argv(cmd: str | None) -> list[str]:
    try:
        return shlex.split(cmd or "")
    except ValueError:
        return []


def _read_path(cmd: str) -> str | None:
    """Path read by `edit view <p>` or a plain bash cat/head/tail/sed -n, else None."""
    argv = _argv(cmd)
    if argv[:2] == ["edit", "view"] and len(argv) > 2:
        return argv[2]
    if argv[:1] == ["bash"]:
        argv = argv[1:]
    # ponytail: no pipes/redirects; the last arg is taken as the path
    if len(argv) > 1 and argv[0] in ("cat", "head", "tail", "sed") and not set("|;&<>") & set(cmd):
        return argv[-1] if not argv[-1].startswith("-") else None
    return None


def live_reads(turns: list[TurnRecord], observations: dict[str, ObservationRecord]) -> set[str]:
    """Obs ids of file reads whose path was not edited since and not re-read by the same cmd.

    These stay unfolded: folding a still-valid read makes small models re-read it forever.
    """
    live: dict[str, tuple[str, str]] = {}  # cmd -> (obs_id, path)
    for turn in turns:
        if turn.obs_id in observations:
            cmd = observations[turn.obs_id].cmd
            if (path := _read_path(cmd)) is not None:
                live[cmd] = (turn.obs_id, path)
        elif turn.role == "assistant":
            argv = _argv(turn.tool_cmd)
            if argv[:2] in (["edit", "write"], ["edit", "replace"]) and len(argv) > 2:
                live = {c: v for c, v in live.items() if v[1] != argv[2]}
    return {obs_id for obs_id, _ in live.values()}


class ContextAssembler:
    """Assembles KV-cache-friendly prompts with deterministic observation folding."""

    def __init__(
        self,
        *,
        fold_after_turns: int = 2,
        fold_char_threshold: int = 200,
        active_char_cap: int = 2400,
        max_context_tokens: int = 8192,
        structured: bool = False,
        mem_enabled: bool = True,
    ) -> None:
        self.fold_after_turns = fold_after_turns
        self.fold_char_threshold = fold_char_threshold
        self.active_char_cap = active_char_cap
        self.max_context_tokens = max_context_tokens
        # True: replay past actions as tool_calls + tool results (provider adapters translate);
        # False: textual fallback for providers without tool messages.
        self.structured = structured
        self.mem_enabled = mem_enabled
        self._static_system_prompt: str | None = None

    @staticmethod
    def _action_as_text(turn: TurnRecord) -> dict[str, Any]:
        call_preview = f"act({turn.tool_cmd!r})"
        if turn.tool_stdin:
            call_preview = f"act({turn.tool_cmd!r}, stdin=<{len(turn.tool_stdin)} chars>)"
        text = f"{turn.content}\n{call_preview}".strip() if turn.content else call_preview
        return {"role": "assistant", "content": text}

    @staticmethod
    def _action_as_tool_call(turn: TurnRecord, call_id: str) -> dict[str, Any]:
        # Replay a real (bounded) prefix of stdin, never a `<N chars>` placeholder: a placeholder
        # can be copied literally into a real argument, while a genuine prefix is valid input.
        args: dict[str, str] = {"cmd": turn.tool_cmd or ""}
        if turn.tool_stdin:
            stdin = turn.tool_stdin
            args["stdin"] = stdin[:STDIN_REPLAY_CHARS] + (
                "\u2026" if len(stdin) > STDIN_REPLAY_CHARS else ""
            )
        return {
            "role": "assistant",
            "content": turn.content or "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "act", "arguments": args},
                }
            ],
        }

    def build_system_prompt(
        self,
        toolbox_index: str,
        skill_instructions: str | None = None,
    ) -> str:
        """Build the immutable system prompt prefix once per session."""
        if self._static_system_prompt is not None:
            return self._static_system_prompt

        parts = [
            "You are an autonomous agent on Tether.",
            "Use `act(cmd, stdin)` to run commands. Run `<cmd> --help` for flags.",
            'Call `act("done", stdin="<final answer>")` when finished.',
            "",
            "[TOOLBOX]",
            toolbox_index,
        ]
        if skill_instructions and skill_instructions.strip():
            parts.extend(["", "[SKILL]", skill_instructions.strip()])

        self._static_system_prompt = "\n".join(parts)
        return self._static_system_prompt

    def assemble(
        self,
        *,
        system_prompt: str,
        goal: str,
        turns: list[TurnRecord],
        observations: dict[str, ObservationRecord],
        pins: dict[str, str],
        current_step: int,
    ) -> list[dict[str, Any]]:
        """Assemble the message array while preserving the static prefix and folding old outputs."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Goal: {goal}"},
        ]

        # History is a list of groups so trimming never splits a tool call from its result.
        groups: list[list[dict[str, Any]]] = []
        pending: TurnRecord | None = None  # assistant action awaiting its tool result

        def flush_pending() -> None:
            nonlocal pending
            if pending is not None:
                groups.append([self._action_as_text(pending)])
                pending = None

        keep = live_reads(turns, observations)
        for turn in turns:
            content = turn.content
            if turn.obs_id and turn.obs_id in observations:
                obs = observations[turn.obs_id]
                age = current_step - turn.step
                if (
                    age >= self.fold_after_turns
                    and obs.char_len >= self.fold_char_threshold
                    and obs.id not in keep
                ):
                    if not self.mem_enabled:
                        content = (
                            obs.summary.split(" | use ")[0] + " | re-run the command if needed]"
                        )
                    else:
                        content = obs.summary
                else:
                    content = elide_active_observation(
                        obs.id,
                        obs.raw_output,
                        max_chars=self.active_char_cap,
                        mem_enabled=self.mem_enabled,
                    )

            if turn.role == "assistant" and turn.tool_cmd:
                flush_pending()
                if self.structured:
                    pending = turn
                else:
                    groups.append([self._action_as_text(turn)])
            elif turn.role == "tool":
                if pending is not None:
                    call_id = f"call_{pending.id}"
                    groups.append(
                        [
                            self._action_as_tool_call(pending, call_id),
                            {"role": "tool", "tool_call_id": call_id, "content": content},
                        ]
                    )
                    pending = None
                else:
                    groups.append([{"role": "user", "content": f"Observation:\n{content}"}])
            else:
                flush_pending()
                groups.append([{"role": turn.role, "content": content}])
        flush_pending()

        pin_block = ""
        if pins:
            pin_lines = ["[PINNED MEMORY]"] + [f"- {k}: {v}" for k, v in pins.items()]
            pin_block = "\n".join(pin_lines)

        # Enforce max_context_tokens by dropping oldest groups (call + result together)
        base_tokens = estimate_messages_tokens(messages, [ACT_TOOL_SCHEMA]) + estimate_tokens(
            pin_block
        )
        while len(groups) > 1 and sum(len(g) for g in groups) > 2:
            flat = [m for g in groups for m in g]
            if base_tokens + estimate_messages_tokens(flat) <= self.max_context_tokens:
                break
            groups.pop(0)
        history_msgs = [m for g in groups for m in g]

        if pin_block:
            if history_msgs and history_msgs[-1]["role"] == "user":
                history_msgs[-1] = {
                    "role": "user",
                    "content": f"{history_msgs[-1]['content']}\n\n{pin_block}",
                }
            else:
                history_msgs.append({"role": "user", "content": pin_block})

        messages.extend(history_msgs)
        return messages
