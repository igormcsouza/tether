"""Native Ollama `/api/chat` httpx adapter with num_ctx and keep_alive support."""

from __future__ import annotations

import json
import os
import sys
from functools import partial
from typing import Any

import httpx

from tether.context import DEFAULT_CONTEXT_TOKENS, estimate_messages_tokens
from tether.providers.base import (
    ActionCall,
    ModelResponse,
    ProviderError,
    action_from_tool_call,
    context_overflow,
    extract_fallback_action,
    limiter_for,
    post_with_retry,
    rejected_call,
)

# Request-level keys of /api/chat; everything else in `params` is a sampling option.
_TOP_LEVEL = frozenset({"think", "keep_alive", "format", "stream"})


# A thinking reply needs room: below this many free tokens the window fills up mid-thought,
# Ollama cuts the reply and the turn comes back empty (#183).
THINK_HEADROOM = 3072
# Healthy thinking is <= ~1.2k tokens at p95. A thinking turn that thinks past this with no
# reply yet is runaway thinking (#173); the stream is cut there (AD-29).
THINK_BUDGET = 2048
# num_predict of every turn unless the caller sets one: THINK_BUDGET 2,048 for thinking plus
# 3,072 for the reply. Above every healthy turn measured (p99 2.2k, max ~2.6k), so it is only a
# safety ceiling against a reply that repeats itself (AD-29).
REPLY_CEILING = 5120


async def _stream(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    """Read a budgeted turn as NDJSON and cut its thinking at THINK_BUDGET (AD-29).

    Returns the turn as one JSON body, the shape `generate` reads. Leaving the `async with`
    closes the connection, so a runaway thought is not generated any further.
    """
    async with client.stream("POST", url, **kwargs) as r:
        if r.status_code != 200:
            await r.aread()
            return httpx.Response(
                r.status_code, content=r.content, headers=r.headers, request=r.request
            )
        thinking: list[str] = []
        content: list[str] = []
        tool_calls: list[Any] = []
        last: dict[str, Any] = {}
        cut = False
        async for line in r.aiter_lines():
            if not line.strip():
                continue
            last = json.loads(line)
            if "error" in last:  # a failure mid-stream: same 500 the non-stream call returns
                return httpx.Response(500, json={"error": last["error"]}, request=r.request)
            msg = last.get("message") or {}
            if msg.get("thinking"):
                thinking.append(str(msg["thinking"]))
            if msg.get("content"):
                content.append(str(msg["content"]))
            tool_calls = msg.get("tool_calls") or tool_calls
            if last.get("done"):
                break
            if len(thinking) >= THINK_BUDGET and not content and not tool_calls:
                cut = True
                break
        if cut:  # no prompt count and the thinking chunks as the completion count
            data: dict[str, Any] = {
                "message": {"role": "assistant", "content": "", "thinking": "".join(thinking)},
                "done_reason": "length",
                "prompt_eval_count": 0,
                "eval_count": len(thinking),
            }
        else:
            data = {
                "message": {
                    "role": "assistant",
                    "content": "".join(content),
                    "thinking": "".join(thinking),
                    "tool_calls": tool_calls,
                },
                "done_reason": last.get("done_reason"),
                "prompt_eval_count": last.get("prompt_eval_count", 0),
                "eval_count": last.get("eval_count", 0),
            }
        return httpx.Response(200, json=data, request=r.request)


def _response(data: dict[str, Any]) -> ModelResponse:
    msg = data.get("message") or {}
    content = str(msg.get("content") or "").strip()
    thinking = str(msg.get("thinking") or "").strip()
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
        thinking=thinking,
        empty=_is_empty(data),
    )


def _is_empty(data: dict[str, Any]) -> bool:
    msg = data.get("message") or {}
    no_text = not str(msg.get("content") or "").strip()
    return no_text and not msg.get("tool_calls") and not msg.get("thinking")


def _empty_marker(model: str) -> str:
    return f"[empty reply from ollama/{model}: no text and no tool call, twice]"


class OllamaProvider:
    """Thin async adapter for Ollama `/api/chat`."""

    structured_history = True  # /api/chat accepts assistant tool_calls and role "tool"

    def __init__(
        self,
        model_name: str = "qwen3.5:9b",
        *,
        host: str | None = None,
        num_ctx: int = DEFAULT_CONTEXT_TOKENS,
        keep_alive: str = "10m",
        timeout: float = 300.0,
        client: httpx.AsyncClient | None = None,
        rpm: int | None = None,
        params: dict[str, Any] | None = None,
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
        self._base_ctx = num_ctx
        self.keep_alive = keep_alive
        self.timeout = timeout
        self._client = client
        self.params = dict(params or {})
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

    async def _chat(
        self, client: httpx.AsyncClient, payload: dict[str, Any], *, stream: bool = False
    ) -> httpx.Response:
        return await post_with_retry(
            client,
            f"{self.host}/api/chat",
            provider="ollama",
            model=self.model_name,
            timeout=self.timeout,
            limiter=self._limiter,
            send=partial(_stream, client) if stream else None,
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
        *,
        answer_only: bool = False,
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {**m, "tool_name": "act"} if m.get("role") == "tool" else m for m in messages
            ],
            **({} if answer_only else {"tools": tools}),
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx},  # sampling is the model's own (#173)
        }
        if self.num_ctx - estimate_messages_tokens(messages, tools) < THINK_HEADROOM:
            payload["think"] = False  # an explicit `think` param below still wins
        for key, value in self.params.items():  # top-level request keys vs sampling options
            if key in _TOP_LEVEL:
                payload[key] = value
            else:
                payload["options"][key] = value
        if "num_predict" not in self.params:
            payload["options"]["num_predict"] = REPLY_CEILING
        budgeted = payload.get("think") is not False and "num_predict" not in self.params
        if budgeted:  # streamed, so thinking is cut at THINK_BUDGET (AD-29)
            payload["stream"] = True
        client = self._get_client()
        resp = await self._chat(client, payload, stream=budgeted)
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
                resp = await self._chat(client, payload, stream=budgeted)
        rejected = rejected_call(resp)
        if rejected is not None and not budgeted:
            return rejected
        if context_overflow(resp):
            # Prompt longer than num_ctx: grow the window once (capped at 4x), the larger one sticks
            if self.num_ctx < self._base_ctx * 4:
                self.num_ctx = min(self.num_ctx * 2, self._base_ctx * 4)
                payload["options"]["num_ctx"] = self.num_ctx
                resp = await self._chat(client, payload, stream=budgeted)
            if context_overflow(resp):
                raise ProviderError(
                    f"ollama model `{self.model_name}`: the prompt does not fit num_ctx "
                    f"{self.num_ctx}; lower --context-tokens or raise the model's context window"
                )
        empty = False
        if rejected is None:
            resp.raise_for_status()
            data = resp.json()
            first = _response(data)
            cut = budgeted and data.get("done_reason") == "length" and first.action is None
            empty = first.empty and data.get("done_reason") != "length"
        else:  # the ceiling cut a tool call mid-way: Ollama cannot parse it (500) and sends no
            # count (tool-call tokens are not streamed either), so the call counts its num_predict
            spent = int(payload["options"].get("num_predict") or REPLY_CEILING)
            first = ModelResponse(content="", completion_tokens=spent)
            cut = True
        if cut:
            # cut by the budget without a command: ask the same turn once more, thinking off
            retry = {**payload, "think": False, "stream": False}  # keeps num_predict (AD-29)
            resp = await self._chat(client, retry)
            if rejected := rejected_call(resp):
                return rejected
            resp.raise_for_status()
            second = _response(resp.json())
            # a cut call with no prompt count (Ollama sent none) counts the re-sent prompt twice
            prompt = (
                first.prompt_tokens + second.prompt_tokens
                if first.prompt_tokens
                else 2 * second.prompt_tokens
            )
            return ModelResponse(
                content=second.content,
                action=second.action,
                prompt_tokens=prompt,
                completion_tokens=first.completion_tokens + second.completion_tokens,
            )
        if empty:
            # no text and no tool call: the identical payload once more, never after a budget cut
            resp = await self._chat(client, payload, stream=budgeted)
            resp.raise_for_status()
            second = _response(resp.json())
            prompt_total = first.prompt_tokens + second.prompt_tokens
            completion_total = first.completion_tokens + second.completion_tokens
            if second.empty:
                return ModelResponse(
                    content=_empty_marker(self.model_name),
                    empty=True,
                    prompt_tokens=prompt_total,
                    completion_tokens=completion_total,
                )
            return ModelResponse(
                content=second.content,
                action=second.action,
                prompt_tokens=prompt_total,
                completion_tokens=completion_total,
            )
        return first
