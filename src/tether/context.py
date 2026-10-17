"""State Plane: ContextAssembler, Ephemeral Observation Folding, and Token Estimator."""

from __future__ import annotations

import json
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


def elide_active_observation(obs_id: str, raw_output: str, max_chars: int = 2400) -> str:
    """Slice oversized active observations into Head + Tail in L1."""
    if len(raw_output) <= max_chars:
        return f"[{obs_id}] {raw_output}"
    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len
    elided_count = len(raw_output) - (head_len + tail_len)
    head = raw_output[:head_len].rstrip()
    tail = raw_output[-tail_len:].lstrip()
    marker = (
        f"\n... [{obs_id}: {elided_count:,} middle chars elided in L1 | "
        f"use `mem search <query>` or `mem recall {obs_id}`] ...\n"
    )
    return f"[{obs_id}] {head}{marker}{tail}"


class ContextAssembler:
    """Assembles KV-cache-friendly prompts with deterministic observation folding."""

    def __init__(
        self,
        *,
        fold_after_turns: int = 2,
        fold_char_threshold: int = 200,
        active_char_cap: int = 2400,
        max_context_tokens: int = 8192,
    ) -> None:
        self.fold_after_turns = fold_after_turns
        self.fold_char_threshold = fold_char_threshold
        self.active_char_cap = active_char_cap
        self.max_context_tokens = max_context_tokens
        self._static_system_prompt: str | None = None

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

        history_msgs: list[dict[str, Any]] = []
        for turn in turns:
            content = turn.content
            if turn.obs_id and turn.obs_id in observations:
                obs = observations[turn.obs_id]
                age = current_step - turn.step
                if age >= self.fold_after_turns and obs.char_len >= self.fold_char_threshold:
                    content = obs.summary
                else:
                    content = elide_active_observation(
                        obs.id, obs.raw_output, max_chars=self.active_char_cap
                    )

            if turn.role == "assistant" and turn.tool_cmd:
                call_preview = f"act({turn.tool_cmd!r})"
                if turn.tool_stdin:
                    call_preview = f"act({turn.tool_cmd!r}, stdin=<{len(turn.tool_stdin)} chars>)"
                text = f"{content}\n{call_preview}".strip() if content else call_preview
                history_msgs.append({"role": "assistant", "content": text})
            elif turn.role == "tool":
                history_msgs.append({"role": "user", "content": f"Observation:\n{content}"})
            else:
                history_msgs.append({"role": turn.role, "content": content})

        pin_block = ""
        if pins:
            pin_lines = ["[PINNED MEMORY]"] + [f"- {k}: {v}" for k, v in pins.items()]
            pin_block = "\n".join(pin_lines)

        # Enforce max_context_tokens by dropping oldest turns if needed
        base_tokens = estimate_messages_tokens(messages, [ACT_TOOL_SCHEMA]) + estimate_tokens(
            pin_block
        )
        while len(history_msgs) > 2:
            total = base_tokens + estimate_messages_tokens(history_msgs)
            if total <= self.max_context_tokens:
                break
            history_msgs.pop(0)

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
