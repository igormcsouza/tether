"""OpenAI-compatible `/v1/chat/completions` httpx adapter (GPT, OpenRouter, vLLM, Groq)."""

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


class OpenAIProvider:
    """Thin async adapter for OpenAI-compatible `/v1/chat/completions` endpoints."""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
        self.timeout = timeout

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or [{}]
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "").strip()
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)

        action: ActionCall | None = None
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            first_tc = tool_calls[0]
            fn_obj = first_tc.get("function") or {}
            raw_args = fn_obj.get("arguments") or "{}"
            action = parse_tool_arguments(raw_args)

        if action is None and content:
            action = extract_fallback_action(content)

        return ModelResponse(content=content, action=action, prompt_tokens=prompt_tokens)
