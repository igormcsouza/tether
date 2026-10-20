"""Tests for the shared bounded retry in tether/providers/base.py."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from tether.providers.base import ProviderError, post_with_retry
from tether.providers.declarative import build_declared, load_declared
from tether.providers.openai import OpenAIProvider


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _post(client: httpx.AsyncClient, sleeps: list[float]) -> httpx.Response:
    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    return await post_with_retry(
        client, "http://x/y", provider="p", model="m", timeout=5.0, sleep=fake_sleep, json={}
    )


async def test_timeout_then_success() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("t", request=request)
        return httpx.Response(200)

    sleeps: list[float] = []
    resp = await _post(_client(handler), sleeps)
    assert resp.status_code == 200 and calls == 2 and sleeps == [1.0]


async def test_exhausted_timeouts_name_provider_model_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("t", request=request)

    sleeps: list[float] = []
    with pytest.raises(ProviderError) as ei:
        await _post(_client(handler), sleeps)
    msg = str(ei.value)
    for part in ("p model", "`m`", "timeout 5s", "3 attempts", "ConnectTimeout"):
        assert part in msg
    assert sleeps == [1.0, 2.0]


async def test_4xx_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    sleeps: list[float] = []
    resp = await _post(_client(handler), sleeps)
    assert resp.status_code == 401 and calls == 1 and sleeps == []


async def test_5xx_retried_then_success() -> None:
    codes = iter([503, 200])
    resp = await _post(_client(lambda r: httpx.Response(next(codes))), [])
    assert resp.status_code == 200


async def test_429_exhausted() -> None:
    with pytest.raises(ProviderError, match="HTTP 429"):
        await _post(_client(lambda r: httpx.Response(429)), [])


async def test_openai_provider_wires_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("tether.providers.base.asyncio.sleep", no_sleep)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("t", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    provider = OpenAIProvider("m", api_key="k", client=_client(handler))
    assert (await provider.generate([], [])).content == "hello"


def test_declared_http_kinds_honour_timeout() -> None:
    for kind in ("openai", "ollama", "anthropic"):
        built = build_declared({"kind": kind, "timeout": 7}, "m", num_ctx=1024)
        assert built.timeout == 7  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", ["openai", "ollama", "anthropic"])
def test_bad_timeout_on_http_kind_rejected(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "p.yaml"
    f.write_text(f"x:\n  kind: {kind}\n  timeout: -1\n")
    monkeypatch.setenv("TETHER_PROVIDERS", str(f))
    with pytest.raises(ValueError, match="providers.yaml: .*timeout"):
        load_declared()


async def test_cancelled_error_passes_through() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _post(_client(handler), [])


async def test_exhausted_error_includes_body_snippet() -> None:
    with pytest.raises(ProviderError, match="overloaded"):
        await _post(_client(lambda r: httpx.Response(503, text="overloaded")), [])
