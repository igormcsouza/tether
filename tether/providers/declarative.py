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
from tether.providers.base import (
    ActionCall,
    Dialect,
    ModelProvider,
    ModelResponse,
    extract_fallback_action,
)
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider

VALID_KINDS = ("openai", "ollama", "anthropic", "command")
BUILTIN_PREFIXES = ("ollama", "openai", "anthropic", "claude")

_SYSTEM_SUFFIX = (
    "\n\nReply with ONLY one JSON object, no prose, no code fence: "
    '{"cmd": "<command>", "stdin": "<optional multiline payload or null>"}'
)

ACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"cmd": {"type": "string"}, "stdin": {"type": ["string", "null"]}},
    "required": ["cmd"],
}
_SCHEMA_JSON = json.dumps(ACT_SCHEMA, separators=(",", ":"))


def _build_dialects(entries: list[dict[str, Any]] | None) -> list[Dialect]:
    """Turn validated `dialects:` entries into extractor callables."""
    built: list[Dialect] = []
    for entry in entries or []:
        pattern = re.compile(entry["regex"], re.DOTALL)
        built.append(_make_dialect(pattern))
    return built


def _make_dialect(pattern: re.Pattern[str]) -> Dialect:
    def extract(text: str) -> ActionCall | None:
        match = pattern.search(text)
        if not match:
            return None
        cmd = (match.group("cmd") or "").strip()
        if not cmd:
            return None
        stdin = match.group("stdin") if "stdin" in pattern.groupindex else None
        return ActionCall(cmd=cmd, stdin=stdin)

    return extract


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
    dialects = cfg.get("dialects")
    if dialects is not None:
        if not isinstance(dialects, list):
            raise _bad(name, "has invalid `dialects` (must be a list of mappings)")
        for item in dialects:
            if not isinstance(item, dict) or not isinstance(item.get("regex"), str):
                raise _bad(name, "has invalid `dialects` item (mapping with `regex` required)")
            try:
                compiled = re.compile(item["regex"], re.DOTALL)
            except re.error as exc:
                raise _bad(name, f"has invalid `dialects` regex ({exc})") from exc
            if "cmd" not in compiled.groupindex:
                raise _bad(name, "has `dialects` regex without a named group `cmd`")
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
        for key in ("context_tokens", "fold_after"):
            if key in cfg:
                val = cfg[key]
                if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                    raise ValueError(
                        f"providers.yaml: entry `{name}` has invalid `{key}` "
                        "(must be a positive integer)"
                    )
        timeout = cfg.get("timeout")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
        ):
            raise _bad(name, "has invalid `timeout` (must be a positive number)")
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
        dialects: list[Dialect] | None = None,
    ) -> None:
        self.model_name = model_name
        self.argv = argv
        self.reply = reply
        self.stdin = stdin if stdin is not None else "{conversation}"
        self.usage = usage or {}
        self.timeout = timeout
        self.dialects = dialects or []

    def _render(self, template: str, system: str, conversation: str) -> str:
        return (
            template.replace("{model}", self.model_name)
            .replace("{system}", system)
            .replace("{conversation}", conversation)
            .replace("{schema}", _SCHEMA_JSON)
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
        if not isinstance(value, str | dict) and isinstance(payload, dict):
            value = payload.get("structured_output")
        action: ActionCall | None
        if isinstance(value, dict) and isinstance(value.get("cmd"), str):
            stdin_val = value.get("stdin")
            action = ActionCall(
                cmd=value["cmd"], stdin=stdin_val if isinstance(stdin_val, str) else None
            )
            text = json.dumps(value)
        else:
            text = value if isinstance(value, str) else ""
            action = extract_fallback_action(text, extra=self.dialects)
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
            dialects=_build_dialects(cfg.get("dialects")),
        )
    http_timeout = {"timeout": cfg["timeout"]} if "timeout" in cfg else {}
    api_key_env = cfg.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if kind == "openai":
        return OpenAIProvider(
            model_name, api_key=api_key, base_url=cfg.get("base_url"), **http_timeout
        )
    if kind == "ollama":
        return OllamaProvider(model_name, host=cfg.get("host"), num_ctx=num_ctx, **http_timeout)
    return AnthropicProvider(
        model_name, api_key=api_key, base_url=cfg.get("base_url"), **http_timeout
    )
