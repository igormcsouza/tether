"""Native Ollama `/api/chat` httpx adapter with num_ctx and keep_alive support."""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

from tether.providers.base import (
    ActionCall,
    ModelResponse,
    action_from_tool_call,
    extract_fallback_action,
    limiter_for,
    post_with_retry,
)


class OllamaProvider:
    """Thin async adapter for Ollama `/api/chat`."""

    structured_history = True  # /api/chat accepts assistant tool_calls and role "tool"

    def __init__(
        self,
        model_name: str = "qwen3.5:9b",
        *,
        host: str | None = None,
        num_ctx: int = 8192,
        keep_alive: str = "10m",
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
        rpm: int | None = None,
        fallback: bool | None = None,
    ) -> None:
        self.model_name = model_name
        self.fallback = (
            os.environ.get("TETHER_OLLAMA_FALLBACK", "") not in ("", "0")
            if fallback is None
            else fallback
        )
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.timeout = timeout
        self._client = client
        self._limiter = limiter_for(f"ollama:{self.host}", rpm)

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
        models = await self._installed_models(client)
        if not models:
            return None
        # Prefer any installed Qwen model first
        for m in models:
            if "qwen" in m.lower():
                return m
        return models[0]

    async def _chat(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> httpx.Response:
        return await post_with_retry(
            client,
            f"{self.host}/api/chat",
            provider="ollama",
            model=self.model_name,
            timeout=self.timeout,
            limiter=self._limiter,
            json=payload,
        )

    async def _installed_models(self, client: httpx.AsyncClient) -> list[str]:
        try:
            resp = await client.get(f"{self.host}/api/tags")
            resp.raise_for_status()
            names = [str(m.get("name") or "") for m in (resp.json().get("models") or [])]
            return [n for n in names if n]
        except Exception:
            return []

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {**m, "tool_name": "act"} if m.get("role") == "tool" else m for m in messages
            ],
            "tools": tools,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
        }
        client = self._get_client()
        resp = await self._chat(client, payload)
        if resp.status_code == 404:
            if not self.fallback:
                raise RuntimeError(
                    f"Ollama model `{self.model_name}` not found; installed: "
                    f"{', '.join(await self._installed_models(client)) or 'none'} "
                    "(set TETHER_OLLAMA_FALLBACK=1 to substitute an installed model)"
                )
            fallback = await self._resolve_installed_model(client)
            if fallback and fallback != self.model_name:
                print(
                    f"tether: warning: ollama model `{self.model_name}` not found, "
                    f"using `{fallback}`",
                    file=sys.stderr,
                )
                self.model_name = fallback
                payload["model"] = fallback
                resp = await self._chat(client, payload)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message") or {}
        content = str(msg.get("content") or "").strip()
        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)

        action: ActionCall | None = None
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            first_tc = tool_calls[0]
            fn_obj = first_tc.get("function") or {}
            action = action_from_tool_call(fn_obj.get("name"), fn_obj.get("arguments") or {})

        if action is None and content:
            action = extract_fallback_action(content)

        return ModelResponse(
            content=content,
            action=action,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
