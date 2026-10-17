"""Native Ollama `/api/chat` httpx adapter with num_ctx and keep_alive support."""

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


class OllamaProvider:
    """Thin async adapter for Ollama `/api/chat`."""

    def __init__(
        self,
        model_name: str = "qwen3.5:9b",
        *,
        host: str | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "10m",
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model_name
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
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

    async def _resolve_installed_model(self, client: httpx.AsyncClient) -> str | None:
        """Query Ollama `/api/tags` to find an installed Qwen (or fallback) model if 404."""
        try:
            resp = await client.get(f"{self.host}/api/tags")
            resp.raise_for_status()
            models = [str(m.get("name") or "") for m in (resp.json().get("models") or [])]
            models = [m for m in models if m]
            if not models:
                return None
            # Prefer any installed Qwen model first
            for m in models:
                if "qwen" in m.lower():
                    return m
            return models[0]
        except Exception:
            return None

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
        }
        client = self._get_client()
        resp = await client.post(f"{self.host}/api/chat", json=payload)
        if resp.status_code == 404:
            fallback = await self._resolve_installed_model(client)
            if fallback and fallback != self.model_name:
                self.model_name = fallback
                payload["model"] = fallback
                resp = await client.post(f"{self.host}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message") or {}
        content = str(msg.get("content") or "").strip()
        prompt_tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)

        action: ActionCall | None = None
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            first_tc = tool_calls[0]
            fn_obj = first_tc.get("function") or {}
            fn_name = str(fn_obj.get("name") or "")
            raw_args = fn_obj.get("arguments") or {}
            action = parse_tool_arguments(raw_args)
            if action is None and fn_name and fn_name != "act":
                # Graceful 9B fallback if model called tool name directly
                if isinstance(raw_args, dict):
                    arg_str = " ".join(f"--{k} {v!r}" for k, v in raw_args.items())
                    action = ActionCall(cmd=f"{fn_name} {arg_str}".strip())
                else:
                    action = ActionCall(cmd=fn_name)

        if action is None and content:
            action = extract_fallback_action(content)

        return ModelResponse(content=content, action=action, prompt_tokens=prompt_tokens)
