"""OpenAI-compatible `/v1/chat/completions` httpx adapter (GPT, OpenRouter, vLLM, Groq)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from tether.providers.base import (
    ActionCall,
    ModelResponse,
    extract_fallback_action,
    parse_tool_arguments,
    post_with_retry,
)


def _to_openai(msg: dict[str, Any]) -> dict[str, Any]:
    """OpenAI wants tool-call `arguments` as a JSON string, not an object."""
    if not msg.get("tool_calls"):
        return msg
    calls = [
        {**tc, "function": {**tc["function"], "arguments": json.dumps(tc["function"]["arguments"])}}
        for tc in msg["tool_calls"]
    ]
    return {**msg, "tool_calls": calls}


class OpenAIProvider:
    """Thin async adapter for OpenAI-compatible `/v1/chat/completions` endpoints."""

    structured_history = True

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
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
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [_to_openai(m) for m in messages],
            "tools": tools,
            "temperature": 0.2,
        }
        client = self._get_client()
        resp = await post_with_retry(
            client,
            f"{self.base_url}/chat/completions",
            provider="openai",
            model=self.model_name,
            timeout=self.timeout,
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
        completion_tokens = int(usage.get("completion_tokens") or 0)

        action: ActionCall | None = None
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            first_tc = tool_calls[0]
            fn_obj = first_tc.get("function") or {}
            raw_args = fn_obj.get("arguments") or "{}"
            action = parse_tool_arguments(raw_args)

        if action is None and content:
            action = extract_fallback_action(content)

        return ModelResponse(
            content=content,
            action=action,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
