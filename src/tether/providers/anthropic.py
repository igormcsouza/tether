"""Native Anthropic `/v1/messages` httpx adapter with automatic `claude -p` OAuth fallback."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any

import httpx

from tether.providers.base import (
    ActionCall,
    ModelResponse,
    extract_fallback_action,
    parse_tool_arguments,
)


class AnthropicProvider:
    """Thin async adapter for Anthropic `/v1/messages` (with `claude` CLI OAuth fallback)."""

    def __init__(
        self,
        model_name: str = "claude-sonnet-5-5",
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 180.0,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
        self.workspace_id = workspace_id or os.environ.get("ANTHROPIC_WORKSPACE_ID") or ""
        self.base_url = (
            base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        ).rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._use_cli_fallback = not bool(self.api_key)

    async def _generate_via_claude_cli(
        self,
        system_text: str,
        chat_msgs: list[dict[str, str]],
    ) -> ModelResponse:
        """Fallback to `claude -p --safe-mode --tools ''` using Claude OAuth subscription."""
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise RuntimeError("Neither valid ANTHROPIC_API_KEY credits nor `claude` CLI found.")

        sys_full = (
            f"{system_text}\n\n"
            'IMPORTANT: Respond ONLY with your next `act("<cmd>", stdin="...")` call.'
        ).strip()

        transcript_parts: list[str] = []
        for m in chat_msgs:
            role_lbl = "User" if m["role"] == "user" else "Assistant"
            transcript_parts.append(f"[{role_lbl}]\n{m['content']}")
        prompt_str = "\n\n".join(transcript_parts)

        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)

        proc = await asyncio.create_subprocess_exec(
            claude_bin,
            "-p",
            "--safe-mode",
            "--tools",
            "",
            "--model",
            self.model_name,
            "--system-prompt",
            sys_full,
            "--output-format",
            "json",
            prompt_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        stdout_str = stdout_b.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0 and not stdout_str:
            err_str = stderr_b.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"claude CLI failed: {err_str}")

        last_line = stdout_str.splitlines()[-1]
        data = json.loads(last_line)
        content = str(data.get("result") or "").strip()
        usage = data.get("usage") or {}
        prompt_tokens = (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("output_tokens") or 0)
        )
        action = extract_fallback_action(content)
        return ModelResponse(content=content, action=action, prompt_tokens=prompt_tokens)

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        system_text = ""
        chat_msgs: list[dict[str, str]] = []
        for m in messages:
            if m.get("role") == "system":
                system_text = str(m.get("content") or "")
            else:
                role = "assistant" if m.get("role") == "assistant" else "user"
                content_str = str(m.get("content") or "").strip() or "(empty)"
                if chat_msgs and chat_msgs[-1]["role"] == role:
                    chat_msgs[-1]["content"] = f"{chat_msgs[-1]['content']}\n\n{content_str}"
                else:
                    chat_msgs.append({"role": role, "content": content_str})

        if self._use_cli_fallback:
            return await self._generate_via_claude_cli(system_text, chat_msgs)

        anthropic_tools: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function") or {}
            anthropic_tools.append(
                {
                    "name": fn.get("name", "act"),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                }
            )

        headers: dict[str, str] = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self.workspace_id:
            headers["anthropic-workspace-id"] = self.workspace_id

        payload: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "messages": chat_msgs,
            "tools": anthropic_tools,
        }
        if system_text:
            payload["system"] = system_text

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 400 and "credit balance" in resp.text.lower():
                self._use_cli_fallback = True
                return await self._generate_via_claude_cli(system_text, chat_msgs)
            resp.raise_for_status()
            data = resp.json()

        text_parts: list[str] = []
        action: ActionCall | None = None
        for block in data.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text") or ""))
            elif btype == "tool_use" and action is None:
                action = parse_tool_arguments(block.get("input") or {})

        content = "\n".join(text_parts).strip()
        if action is None and content:
            action = extract_fallback_action(content)

        usage = data.get("usage") or {}
        prompt_tokens = (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("output_tokens") or 0)
        )
        return ModelResponse(content=content, action=action, prompt_tokens=prompt_tokens)
