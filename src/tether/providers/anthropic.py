"""Native Anthropic `/v1/messages` httpx adapter."""

from __future__ import annotations

import os
from typing import Any

import httpx

from tether.providers.base import (
    ActionCall,
    ModelResponse,
    extract_fallback_action,
    parse_tool_arguments,
)


class AnthropicProvider:
    """Thin async adapter for Anthropic `/v1/messages`."""

    def __init__(
        self,
        model_name: str = "claude-3-7-sonnet-latest",
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
        self.workspace_id = workspace_id or os.environ.get("ANTHROPIC_WORKSPACE_ID") or ""
        self.base_url = (
            base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        ).rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

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
        if anthropic_tools:
            anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}

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
            payload["system"] = [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        client = self._get_client()
        resp = await client.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=payload,
        )
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
