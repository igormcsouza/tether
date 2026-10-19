"""Base provider protocol and 9B fallback tool-call parser."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ActionCall:
    cmd: str
    stdin: str | None = None


@dataclass(slots=True)
class ModelResponse:
    content: str
    action: ActionCall | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


ProviderResponse = ModelResponse


class ModelProvider(Protocol):
    model_name: str

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse: ...


_ACT_CALL_RE = re.compile(
    r"act\(\s*(?P<args>.*)\s*\)",
    re.DOTALL,
)
_MULTILINE_ACT_RE = re.compile(
    r"act\(\s*(?:(?:cmd|command)\s*=\s*)?(?P<q1>\"\"\"|'''|\"|')(?P<cmd>.*?)(?P=q1)"
    r"(?:\s*,\s*(?:stdin\s*=\s*)?(?P<q2>\"\"\"|'''|\"|')(?P<stdin>[\s\S]*)(?P=q2))?\s*\)",
)
_TOOL_XML_RE = re.compile(
    r"<tool_call>\s*(?P<body>.*?)\s*</tool_call>",
    re.DOTALL,
)


def parse_tool_arguments(raw_args: str | dict[str, Any]) -> ActionCall | None:
    """Parse tool arguments from a dict or JSON string into an ActionCall."""
    data: dict[str, Any]
    if isinstance(raw_args, dict):
        data = raw_args
    else:
        try:
            parsed = json.loads(raw_args)
            if not isinstance(parsed, dict):
                return None
            data = parsed
        except Exception:
            return None

    # If the model called `act` with {"cmd": ..., "stdin": ...}
    if "cmd" in data:
        cmd = str(data.get("cmd") or "").strip()
        stdin = str(data["stdin"]) if data.get("stdin") is not None else None
        return ActionCall(cmd=cmd, stdin=stdin) if cmd else None

    if "command" in data:
        cmd = str(data.get("command") or "").strip()
        stdin = str(data["stdin"]) if data.get("stdin") is not None else None
        return ActionCall(cmd=cmd, stdin=stdin) if cmd else None

    return None


_PARAM_CMD_RE = re.compile(r'<parameter\s+name="cmd"\s*>(?P<value>.*?)</parameter>', re.DOTALL)
_PARAM_STDIN_RE = re.compile(r'<parameter\s+name="stdin"\s*>(?P<value>.*?)</parameter>', re.DOTALL)

Dialect = Callable[[str], "ActionCall | None"]


def _dialect_tool_call_json(text: str) -> ActionCall | None:
    """`<tool_call>{json}</tool_call>` blocks (common in Qwen models)."""
    match = _TOOL_XML_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group("body").strip())
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    args = payload.get("arguments") or payload.get("parameters") or payload
    return parse_tool_arguments(args)


def _dialect_raw_json(text: str) -> ActionCall | None:
    """A raw JSON object containing `"cmd"` somewhere in the text."""
    if '"cmd"' not in text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        return parse_tool_arguments(text[start : end + 1])
    return None


def _dialect_parameter_tags(text: str) -> ActionCall | None:
    """`<parameter name="cmd">X</parameter>` with optional `stdin` parameter."""
    cmd_match = _PARAM_CMD_RE.search(text)
    if not cmd_match:
        return None
    cmd = cmd_match.group("value").strip()
    if not cmd:
        return None
    stdin_match = _PARAM_STDIN_RE.search(text)
    return ActionCall(cmd=cmd, stdin=stdin_match.group("value") if stdin_match else None)


def _act_from_ast(args: str) -> ActionCall | None:
    try:
        tree = ast.parse(f"f({args})", mode="eval")
    except SyntaxError:
        return None
    if not isinstance(tree.body, ast.Call):
        return None
    call = tree.body
    cmd_val: str | None = None
    stdin_val: str | None = None
    if call.args and isinstance(call.args[0], ast.Constant):
        cmd_val = str(call.args[0].value)
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        stdin_val = str(call.args[1].value)
    for kw in call.keywords:
        if kw.arg in ("cmd", "command") and isinstance(kw.value, ast.Constant):
            cmd_val = str(kw.value.value)
        elif kw.arg == "stdin" and isinstance(kw.value, ast.Constant):
            stdin_val = str(kw.value.value)
    return ActionCall(cmd=cmd_val, stdin=stdin_val) if cmd_val else None


def _dialect_act_text(text: str) -> ActionCall | None:
    """Python-style `act("...", stdin="...")` call written in plain text."""
    ml_match = _MULTILINE_ACT_RE.search(text)
    if ml_match:
        cmd_str = ml_match.group("cmd").strip()
        if cmd_str:
            return ActionCall(cmd=cmd_str, stdin=ml_match.group("stdin"))
    act_match = _ACT_CALL_RE.search(text)
    if act_match:
        return _act_from_ast(act_match.group("args"))
    return None


DIALECTS: list[Dialect] = [
    _dialect_tool_call_json,
    _dialect_raw_json,
    _dialect_parameter_tags,
    _dialect_act_text,
]


def register_dialect(fn: Dialect) -> Dialect:
    """Append a custom tool-call dialect extractor to `DIALECTS`."""
    DIALECTS.append(fn)
    return fn


def extract_fallback_action(text: str, extra: Iterable[Dialect] = ()) -> ActionCall | None:
    """Extract an ActionCall when a small 9B model emits tool syntax inside plain text."""
    if not text:
        return None
    for dialect in (*DIALECTS, *extra):
        call = dialect(text)
        if call:
            return call
    return None
