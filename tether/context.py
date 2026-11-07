"""State Plane: ContextAssembler, Ephemeral Observation Folding, and Token Estimator."""

from __future__ import annotations

import json
import os
import re
import shlex
from collections import Counter
from pathlib import Path
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
# Default context budget (also Ollama's num_ctx): 32k keeps qwen3.5:9b fully on an 8 GB GPU (#173).
DEFAULT_CONTEXT_TOKENS = 32768


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


_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def (test\w*)", re.M)
TEST_INDEX_MAX = 30


def _elided_tests(raw: str, start: int, end: int) -> str:
    """`name:line` of tests defined in raw[start:end] (#170): a cut test file is not re-read."""
    found = [
        f"{m[1]}:{raw.count(chr(10), 0, start + m.start(1)) + 1}"
        for m in _TEST_DEF.finditer(raw[start:end])
    ]
    if not found:
        return ""
    more = f" +{len(found) - TEST_INDEX_MAX} more" if len(found) > TEST_INDEX_MAX else ""
    return f"\ntests in the elided part: {' '.join(found[:TEST_INDEX_MAX])}{more}"


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
    index = _elided_tests(raw_output, head_len, len(raw_output) - tail_len)
    return f"[{obs_id}] {head}{marker}{index.lstrip(chr(10)) + chr(10) if index else ''}{tail}"


def _argv(cmd: str | None) -> list[str]:
    try:
        return shlex.split(cmd or "")
    except ValueError:
        return []


# Unedited file reads kept unfolded; older ones fold normally. #81 is the real budget backstop.
MAX_LIVE_READS = 8


# Restart (north star): after RESTART_AFTER_FAILS failing check runs separated by edits the
# history is replaced by one bounded message that describes the state and what was tried,
# without replaying the failed commands. Gumaan, "Feedback That Backfires" (arXiv 2608.23651):
# a failed action's verbatim text in the context makes small models repeat it, and a clean
# restart that restores the same context is the worst case, so the new context must differ.
RESTART_AFTER_FAILS = 3
MAX_RESTARTS = 2
RESTART_MAX_CHARS = 6000
_RESTART_FILES_CHARS = 4000
_RESTART_OUTPUT_CHARS = 1500
_SKIP_DIRS = {"__pycache__", "node_modules"}


def after_restart(turns: list[TurnRecord]) -> list[TurnRecord]:
    """The turns from the latest restart message on (all of them when there was none)."""
    for i in range(len(turns) - 1, -1, -1):
        if turns[i].event_type == "restart":
            return turns[i:]
    return turns


def modified_files(root: str | Path, since: float) -> dict[str, str]:
    """Up to 3 text files under `root` written after `since`, newest first (hidden dirs skipped)."""
    found: list[tuple[float, str, str]] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
        for name in names:
            path = Path(dirpath) / name
            try:
                mtime = path.stat().st_mtime
                if mtime >= since:
                    found.append((mtime, str(path.relative_to(root)), path.read_text("utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    return {rel: text for _, rel, text in sorted(found, reverse=True)[:3]}


def describe_attempts(
    files: list[str], changes: list[str], reads: Counter[str], check_cmd: str | None, runs: int
) -> list[str]:
    """What was tried, as counts: no command text from the failed steps is repeated."""
    tried = []
    for name in files:
        n = sum(name in c for c in changes)
        tried += [f"{name} changed {n} times"] if n else []
    tried += [f"{p} read {n} times" for p, n in reads.most_common(3) if n >= 2]
    if check_cmd:
        tried.append(f"`{check_cmd}` run {runs} times with a failing result each time")
    return tried


def restart_message(
    *,
    step: int,
    check_cmd: str | None,
    failing_output: str | None,
    files: dict[str, str],
    tried: list[str],
    handback: int = 0,
    fresh: list[str] | None = None,
    failing: list[str] | None = None,
    best: bool = False,
) -> str:
    """The one message a restarted history starts from, or (`handback` = restarts used) the
    summary handed back to the caller; at most RESTART_MAX_CHARS. `fresh` names the files put
    back as they started (a fresh attempt): the failing output, which quotes the failed code, is
    then left out and `failing` (test names) is listed instead. `best`: the files are back to the
    version that failed only `failing`."""
    share = _RESTART_FILES_CHARS // max(1, len(files))
    blocks = []
    for name, text in files.items():
        cut = f"\n[{len(text) - share} more chars not shown]" if len(text) > share else ""
        blocks.append(f"{name}:\n{text[:share]}{cut}")
    if handback:
        head = f"[STUCK at step {step} after {handback} restarts. Handing back to you.]"
    elif fresh:
        head = (
            f"[RESTART at step {step} with a fresh start. Your last approach kept failing the same "
            f"tests, so it was set aside: {', '.join(fresh)} are back to how they started.]"
        )
    elif best:
        head = (
            f"[RESTART at step {step}. Your later changes kept failing, so your files are back to "
            f"your best version, which failed only: {', '.join(failing or [])}.]"
        )
    else:
        head = f"[RESTART at step {step}. Earlier steps are not shown; files are as you left them.]"
    lines = [head, *(["", "Your files now:", *blocks] if blocks else [])]
    if best:
        lines += [
            "",
            f"Run `{check_cmd}`, then fix only those tests with small edits; keep what passes.",
        ]
        return "\n".join(lines)[:RESTART_MAX_CHARS]
    if fresh:
        failed = ", ".join(failing or [])
        lines += ["", f"Tests that kept failing: {failed}"] if failed else []
        lines += [
            "",
            "Write a new implementation with a different approach; do not rebuild the "
            "one that failed. Read the tests first.",
        ]
        return "\n".join(lines)[:RESTART_MAX_CHARS]
    if failing_output is not None:
        out = failing_output.strip()
        if len(out) > _RESTART_OUTPUT_CHARS:
            out = f"{out[:900]}\n...\n{out[-500:]}"
        lines += ["", f"Last result of `{check_cmd}`:", out]
    lines += ["", "What was tried so far:", *(f"- {t}" for t in tried)]
    lines += [
        "The work is not progressing. Refine the request or give guidance, then send it again."
        if handback
        else "Re-read the failing output above before you change anything."
        if failing_output is not None
        else "Change your approach before you repeat anything."
    ]
    return "\n".join(lines)[:RESTART_MAX_CHARS]


def _read_path(cmd: str) -> str | None:
    """Path read by `edit view <p>` or a pure bash cat/head/tail/sed -n, else None."""
    argv = _argv(cmd)
    if argv[:2] == ["edit", "view"] and len(argv) > 2:
        return argv[2]
    if argv[:1] == ["bash"]:
        argv = argv[1:]
    # ponytail: no pipes/redirects; the last arg is taken as the path
    if len(argv) < 2 or set("|;&<>") & set(cmd) or argv[-1].startswith("-"):
        return None
    in_place = any(a.startswith("-i") or a == "--in-place" for a in argv)
    if argv[0] in ("cat", "head", "tail") or (argv[0] == "sed" and "-n" in argv and not in_place):
        return argv[-1]
    return None


def _read_range(cmd: str, path: str) -> str:
    """Line-range args of a read (`--lines 65:120`, `sed -n 65,120p`), so ranges stay apart."""
    skip = {"bash", "edit", "view", "cat", "head", "tail", "sed", "-n", "--lines", path}
    return " ".join(a for a in _argv(cmd) if a not in skip)


def _live_map(
    turns: list[TurnRecord], observations: dict[str, ObservationRecord], root: str = ""
) -> dict[tuple[str, str], str]:
    """Build a map of (normalized path, range) -> obs_id for live reads, oldest first.

    A path stops being live on `edit write|replace` or on any non-read command that
    mentions it (sed -i, tee, `cat > p << EOF`, with or without a `bash` prefix).
    """
    live: dict[tuple[str, str], str] = {}  # (normalized path, cmd) -> obs_id, oldest first

    def norm(p: str) -> str:
        return os.path.normpath(os.path.join(root, p))

    for turn in turns:
        if turn.obs_id in observations:
            cmd = observations[turn.obs_id].cmd
            if (path := _read_path(cmd)) is not None:
                key = (norm(path), _read_range(cmd, path))
                live.pop(key, None)
                live[key] = turn.obs_id
        elif turn.role == "assistant" and turn.tool_cmd:
            argv = _argv(turn.tool_cmd)
            if argv[:2] in (["edit", "write"], ["edit", "replace"]) and len(argv) > 2:
                live = {k: v for k, v in live.items() if k[0] != norm(argv[2])}
            elif _read_path(turn.tool_cmd) is None:  # bash, or a shell write via the bash fallback
                # ponytail: token/substring match; won't catch paths built at runtime
                tokens = {norm(t) for t in argv[1:]}
                live = {
                    k: v
                    for k, v in live.items()
                    if k[0] not in tokens
                    and os.path.relpath(k[0], root or ".") not in turn.tool_cmd
                }
    return live


def live_reads(
    turns: list[TurnRecord], observations: dict[str, ObservationRecord], root: str = ""
) -> set[str]:
    """Obs ids of the latest unedited read per path+range (max MAX_LIVE_READS); never folded.

    Folding a still-valid read makes small models re-read it forever. A path stops being live
    on `edit write|replace` or on any non-read bash command that mentions it (sed -i, tee, ...).
    """
    return set(list(_live_map(turns, observations, root).values())[-MAX_LIVE_READS:])


def live_read_obs(
    cmd: str, turns: list[TurnRecord], observations: dict[str, ObservationRecord], root: str = ""
) -> str | None:
    """Obs id of the live read that `cmd` repeats, else None (edited, folded or never read).

    A read is "live" if the file hasn't been edited since and its output is still in the prompt.
    Only the most recent MAX_LIVE_READS live reads are considered.
    """
    path = _read_path(cmd)
    if path is None:
        return None
    key = (os.path.normpath(os.path.join(root, path)), _read_range(cmd, path))
    live = _live_map(turns, observations, root)
    recent = list(live.values())[-MAX_LIVE_READS:]
    if key not in live or live[key] not in recent:
        return None
    return live[key]


def tombstone(obs: ObservationRecord, mem_enabled: bool = True) -> str:
    """One-line stand-in for a folded observation; recall hint only when `mem` exists."""
    cmd_short = obs.cmd.strip().replace("\n", " ")[:48]
    hint = (
        f"use `mem search <q>` or `mem recall {obs.id}`"
        if mem_enabled
        else "re-run the command if needed"
    )
    return f"[{obs.id} folded: `{cmd_short}` ({obs.char_len:,} chars) | {hint}]"


class ContextAssembler:
    """Assembles KV-cache-friendly prompts with deterministic observation folding."""

    def __init__(
        self,
        *,
        fold_after_turns: int = 2,
        fold_char_threshold: int = 200,
        active_char_cap: int | None = None,
        max_context_tokens: int = DEFAULT_CONTEXT_TOKENS,
        structured: bool = False,
        mem_enabled: bool = True,
        workspace_root: str = "",
    ) -> None:
        self.fold_after_turns = fold_after_turns
        self.fold_char_threshold = fold_char_threshold
        # One observation may use a third of the context (4 chars/token); the budget still folds
        # older ones first, so a 12 KB test file is seen whole instead of head+tail, then re-read.
        self.active_char_cap = (
            max(2400, max_context_tokens * 4 // 3) if active_char_cap is None else active_char_cap
        )
        self.max_context_tokens = max_context_tokens
        # True: replay past actions as tool_calls + tool results (provider adapters translate);
        # False: textual fallback for providers without tool messages.
        self.structured = structured
        self.mem_enabled = mem_enabled
        self.workspace_root = workspace_root
        self._static_system_prompt: str | None = None
        self.calibration = 1.0  # real prompt tokens / our estimate, learned from the provider
        self.overflow = 0  # estimated tokens still over budget after every deterministic step

    def calibrate(self, estimated: int, actual: int) -> None:
        """Learn how far the 4-chars/token estimate undercounts for this model (never below 1)."""
        if estimated > 0 and actual > 0:
            self.calibration = min(1.5, max(1.0, actual / estimated))

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

    def _turn_chars(self, turn: TurnRecord, observations: dict[str, ObservationRecord]) -> int:
        obs = observations.get(turn.obs_id or "")
        body = min(obs.char_len, self.active_char_cap) if obs else len(turn.content or "")
        return body + len(turn.tool_cmd or "") + len(turn.tool_stdin or "")

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

        keep = live_reads(turns, observations, self.workspace_root)
        # While the whole history fits in half the window nothing is folded by age: the model keeps
        # what it read instead of reading it again. The budget below still folds under pressure.
        used = (
            estimate_messages_tokens(messages, [ACT_TOOL_SCHEMA])
            + sum(self._turn_chars(t, observations) for t in turns) // 4
        )
        fold_by_age = used > self.max_context_tokens // 2
        # Live (unfolded) observation messages, oldest first: shrunk in place under budget pressure.
        live: list[tuple[dict[str, Any], ObservationRecord, str]] = []
        for turn in turns:
            content = turn.content
            obs = None
            if turn.obs_id and turn.obs_id in observations:
                obs = observations[turn.obs_id]
                age = current_step - turn.step
                if (
                    fold_by_age
                    and age >= self.fold_after_turns
                    and obs.char_len >= self.fold_char_threshold
                    and obs.id not in keep
                    and not obs.cmd.startswith("mem recall")  # asked for; re-folding loops (#86)
                ):
                    content = tombstone(obs, self.mem_enabled)
                    obs = None
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
                    wrap = ""
                else:
                    groups.append([{"role": "user", "content": f"Observation:\n{content}"}])
                    wrap = "Observation:\n"
                if obs is not None:
                    live.append((groups[-1][-1], obs, wrap))
            else:
                flush_pending()
                groups.append([{"role": turn.role, "content": content}])
        flush_pending()

        pin_block = ""
        if pins:
            pin_lines = ["[PINNED MEMORY]"] + [f"- {k}: {v}" for k, v in pins.items()]
            pin_block = "\n".join(pin_lines)

        # Enforce max_context_tokens deterministically, cheapest loss first (#81):
        # 1. fold live observations oldest-first, 2. drop oldest groups (call + result together),
        # 3. shrink the newest observation. `overflow` > 0 means even that was not enough.
        base_tokens = estimate_messages_tokens(messages, [ACT_TOOL_SCHEMA]) + estimate_tokens(
            pin_block
        )
        # Keep a quarter of the window free for the reply; a full prompt cuts off writes (#144).
        limit = int(self.max_context_tokens * 3 // 4 / self.calibration)

        def over() -> int:
            flat = [m for g in groups for m in g]
            return base_tokens + estimate_messages_tokens(flat) - limit

        for msg, obs, wrap in live[:-1]:
            if over() <= 0:
                break
            msg["content"] = wrap + tombstone(obs, self.mem_enabled)
        while len(groups) > 1 and over() > 0:
            groups.pop(0)
        if over() > 0 and live and live[-1][0] in groups[-1]:
            msg, obs, wrap = live[-1]
            cap = max(400, min(self.active_char_cap, len(msg["content"])) - over() * 4)
            msg["content"] = wrap + elide_active_observation(
                obs.id, obs.raw_output, max_chars=cap, mem_enabled=self.mem_enabled
            )
        self.overflow = max(0, over())
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
