"""Declarative providers loaded from ~/.tether/providers.yaml."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from tether.providers.anthropic import AnthropicProvider
from tether.providers.base import ActionCall, ModelProvider, ModelResponse, extract_fallback_action
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider

VALID_KINDS = ("openai", "ollama", "anthropic", "command")
BUILTIN_PREFIXES = ("ollama", "openai", "anthropic", "claude")

_SYSTEM_SUFFIX = (
    "\n\nReply with ONLY one JSON object, no prose, no code fence: "
    '{"cmd": "<command>", "stdin": "<optional multiline payload or null>"}'
)
_XML_CMD_RE = re.compile(r'<parameter name="cmd">(?P<v>.*?)</parameter>', re.DOTALL)
_XML_STDIN_RE = re.compile(r'<parameter name="stdin">(?P<v>.*?)</parameter>', re.DOTALL)


def providers_path() -> Path:
    """Return the providers file path (TETHER_PROVIDERS overrides the default)."""
    env = os.environ.get("TETHER_PROVIDERS")
    if env:
        return Path(env)
    return Path.home() / ".tether" / "providers.yaml"


def _bad(name: Any, problem: str) -> ValueError:
    return ValueError(f"providers.yaml: entry `{name}` {problem}")


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) for v in value)


def _validate_command(name: Any, cfg: dict[str, Any]) -> None:
    if not _is_str_list(cfg.get("argv")):
        raise _bad(name, "kind `command` requires `argv` (non-empty list of strings)")
    reply = cfg.get("reply")
    if not isinstance(reply, str) or not reply:
        raise _bad(name, "kind `command` requires `reply` (dotted JSON path string)")
    stdin = cfg.get("stdin")
    if stdin is not None and not isinstance(stdin, str):
        raise _bad(name, "has invalid `stdin` (must be a string template)")
    timeout = cfg.get("timeout")
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
    ):
        raise _bad(name, "has invalid `timeout` (must be a positive number)")
    usage = cfg.get("usage")
    if usage is None:
        return
    if not isinstance(usage, dict):
        raise _bad(name, "has invalid `usage` (must be a mapping)")
    prompt = usage.get("prompt")
    if prompt is not None and not (isinstance(prompt, str) or _is_str_list(prompt)):
        raise _bad(name, "has invalid `usage.prompt` (path string or list of path strings)")
    completion = usage.get("completion")
    if completion is not None and not isinstance(completion, str):
        raise _bad(name, "has invalid `usage.completion` (path string)")


def load_declared() -> dict[str, dict[str, Any]]:
    """Load and validate declared providers; returns {} if the file is missing."""
    path = providers_path()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("providers.yaml: top level must be a mapping of name -> mapping")
    result: dict[str, dict[str, Any]] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"providers.yaml: entry `{name}` must be a mapping")
        if str(name).lower() in BUILTIN_PREFIXES:
            raise ValueError(f"providers.yaml: `{name}` cannot shadow a built-in provider")
        kind = cfg.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(
                f"providers.yaml: entry `{name}` has unknown kind `{kind}`. "
                f"Valid kinds: {', '.join(VALID_KINDS)}."
            )
        if kind == "command":
            _validate_command(name, cfg)
        result[str(name)] = cfg
    return result


def _lookup(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class CommandProvider:
    """Provider that shells out to an external command (argv, never a shell)."""

    structured_history = False

    def __init__(
        self,
        model_name: str,
        *,
        argv: list[str],
        reply: str,
        stdin: str | None = None,
        usage: dict[str, Any] | None = None,
        timeout: float = 300,
    ) -> None:
        self.model_name = model_name
        self.argv = argv
        self.reply = reply
        self.stdin = stdin if stdin is not None else "{conversation}"
        self.usage = usage or {}
        self.timeout = timeout

    def _render(self, template: str, system: str, conversation: str) -> str:
        return (
            template.replace("{model}", self.model_name)
            .replace("{system}", system)
            .replace("{conversation}", conversation)
        )

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        system = (
            "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
            + _SYSTEM_SUFFIX
        )
        conversation = "\n\n".join(
            f"[{m.get('role', '')}]\n{m.get('content', '')}"
            for m in messages
            if m.get("role") != "system"
        )
        argv = [self._render(a, system, conversation) for a in self.argv]
        stdin = self._render(self.stdin, system, conversation)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(stdin.encode("utf-8")), timeout=self.timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"command provider `{self.model_name}` timed out after {self.timeout}s"
            ) from None
        out_text = out.decode("utf-8", errors="replace")
        err_text = err.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                f"command provider `{self.model_name}` exited with {proc.returncode}: "
                f"{(err_text or out_text)[:300]}"
            )
        try:
            payload = json.loads(out_text)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"command provider `{self.model_name}` returned invalid JSON: "
                f"{(out_text or err_text)[:300]}"
            ) from None
        value = _lookup(payload, self.reply)
        text = value if isinstance(value, str) else ""
        action = extract_fallback_action(text)
        if action is None:
            cmd_match = _XML_CMD_RE.search(text)
            if cmd_match:
                stdin_match = _XML_STDIN_RE.search(text)
                action = ActionCall(
                    cmd=cmd_match.group("v").strip(),
                    stdin=stdin_match.group("v") if stdin_match else None,
                )
        prompt_paths = self.usage.get("prompt") or []
        if isinstance(prompt_paths, str):
            prompt_paths = [prompt_paths]
        completion_path = self.usage.get("completion")
        return ModelResponse(
            content=text,
            action=action,
            prompt_tokens=sum(_as_int(_lookup(payload, p)) for p in prompt_paths),
            completion_tokens=_as_int(_lookup(payload, completion_path)) if completion_path else 0,
        )


def build_declared(cfg: dict[str, Any], model_name: str, *, num_ctx: int) -> ModelProvider:
    """Build a provider instance from a declared config entry."""
    kind = cfg["kind"]
    if kind == "command":
        return CommandProvider(
            model_name,
            argv=cfg["argv"],
            reply=cfg["reply"],
            stdin=cfg.get("stdin"),
            usage=cfg.get("usage"),
            timeout=cfg.get("timeout", 300),
        )
    api_key_env = cfg.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if kind == "openai":
        return OpenAIProvider(model_name, api_key=api_key, base_url=cfg.get("base_url"))
    if kind == "ollama":
        return OllamaProvider(model_name, host=cfg.get("host"), num_ctx=num_ctx)
    return AnthropicProvider(model_name, api_key=api_key, base_url=cfg.get("base_url"))
