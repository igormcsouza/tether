"""Base provider protocol and 9B fallback tool-call parser."""

from __future__ import annotations

import ast
import json
import re
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


class ModelProvider(Protocol):
    model_name: str

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse: ...


_ACT_CALL_RE = re.compile(
    r"act\(\s*(?P<args>.*?)\s*\)",
    re.DOTALL,
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


def extract_fallback_action(text: str) -> ActionCall | None:
    """Extract an ActionCall when a small 9B model emits tool syntax inside plain text."""
    if not text:
        return None

    # 1. Check <tool_call>...</tool_call> XML blocks (common in Qwen models)
    xml_match = _TOOL_XML_RE.search(text)
    if xml_match:
        body = xml_match.group("body").strip()
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                args = payload.get("arguments") or payload.get("parameters") or payload
                call = parse_tool_arguments(args)
                if call:
                    return call
        except Exception:
            pass

    # 2. Check raw JSON object containing "cmd"
    if '"cmd"' in text:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            call = parse_tool_arguments(text[start : end + 1])
            if call:
                return call

    # 3. Check Python-style `act("...", stdin="...")` call in text
    act_match = _ACT_CALL_RE.search(text)
    if act_match:
        expr = f"f({act_match.group('args')})"
        try:
            tree = ast.parse(expr, mode="eval")
            if isinstance(tree.body, ast.Call):
                cmd_val: str | None = None
                stdin_val: str | None = None
                if tree.body.args and isinstance(tree.body.args[0], ast.Constant):
                    cmd_val = str(tree.body.args[0].value)
                if len(tree.body.args) > 1 and isinstance(tree.body.args[1], ast.Constant):
                    stdin_val = str(tree.body.args[1].value)
                for kw in tree.body.keywords:
                    if kw.arg in ("cmd", "command") and isinstance(kw.value, ast.Constant):
                        cmd_val = str(kw.value.value)
                    elif kw.arg == "stdin" and isinstance(kw.value, ast.Constant):
                        stdin_val = str(kw.value.value)
                if cmd_val:
                    return ActionCall(cmd=cmd_val, stdin=stdin_val)
        except Exception:
            pass

    return None
