"""Tests for the shared bounded retry in tether/providers/base.py."""

from __future__ import annotations

import asyncio
import json
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
        return httpx.Response(404)

    sleeps: list[float] = []
    resp = await _post(_client(handler), sleeps)
    assert resp.status_code == 404 and calls == 1 and sleeps == []


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


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failure_names_env_var_not_value(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="bad key")

    with pytest.raises(ProviderError) as ei:
        await post_with_retry(
            _client(handler),
            "http://x/y",
            provider="openai",
            model="m",
            timeout=5.0,
            key_env="NVIDIA_API_KEY",
            json={},
        )
    msg = str(ei.value)
    assert f"HTTP {status}" in msg and "`NVIDIA_API_KEY`" in msg and calls == 1
    if status == 401:
        assert "is missing or rejected" in msg and "bad key" not in msg
    else:
        assert "access denied (HTTP 403)" in msg and "bad key" in msg
        assert "missing or rejected" not in msg


async def test_auth_failure_without_env_var_name() -> None:
    with pytest.raises(ProviderError, match="the API key is missing or rejected"):
        await _post(_client(lambda r: httpx.Response(401)), [])


async def test_exhausted_error_includes_body_snippet() -> None:
    with pytest.raises(ProviderError, match="overloaded"):
        await _post(_client(lambda r: httpx.Response(503, text="overloaded")), [])


async def test_total_deadline_per_attempt() -> None:
    """A stalled/trickling response is bounded by asyncio.wait_for(timeout)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)  # longer than the 0.05s deadline
        return httpx.Response(200)

    async def no_sleep(_: float) -> None:
        return None

    client = _client(handler)
    with pytest.raises(ProviderError) as exc:
        await post_with_retry(
            client,
            "http://x/y",
            provider="p",
            model="m",
            timeout=0.05,
            retries=1,
            sleep=no_sleep,
            json={},
        )
    msg = str(exc.value)
    assert "TimeoutError" in msg
    assert "timeout 0.05s" in msg
    assert "2 attempts" in msg


async def test_429_waits_longer_and_honors_retry_after() -> None:
    codes = iter([(429, {}), (429, {"retry-after": "7"}), (200, {})])

    def handler(request: httpx.Request) -> httpx.Response:
        code, headers = next(codes)
        return httpx.Response(code, headers=headers)

    sleeps: list[float] = []
    resp = await _post(_client(handler), sleeps)
    assert resp.status_code == 200 and sleeps == [10.0, 7.0]


async def test_persistent_429_gets_more_attempts_with_capped_wait() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    sleeps: list[float] = []
    with pytest.raises(ProviderError, match="5 attempts"):
        await _post(_client(handler), sleeps)
    assert sleeps == [10.0, 20.0, 30.0, 30.0]


@pytest.mark.parametrize("shared", [True, False])
async def test_rate_limiter_blocks_when_window_full(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, shared: bool
) -> None:
    from tether.providers import base
    from tether.providers.base import RateLimiter, limiter_for

    monkeypatch.setenv("TETHER_RATE_DIR", str(tmp_path))
    now = [100.0]
    slept: list[float] = []

    async def fake_sleep(d: float) -> None:
        slept.append(d)
        now[0] += d

    monkeypatch.setattr(base.time, "time", lambda: now[0])
    monkeypatch.setattr(base.asyncio, "sleep", fake_sleep)
    lim = RateLimiter(2, "k" if shared else "")
    other = RateLimiter(2, "k" if shared else "")  # a second process sharing the same file
    await lim.acquire()
    now[0] += 10
    await (other if shared else lim).acquire()
    await lim.acquire()  # third call must wait until the first leaves the 60 s window
    assert slept == [pytest.approx(50.0)]
    assert limiter_for("k", None) is None
    assert limiter_for("k", 5) is limiter_for("k", 5)


async def test_rate_limiter_recovers_from_a_corrupt_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tether.providers.base import RateLimiter

    monkeypatch.setenv("TETHER_RATE_DIR", str(tmp_path))
    lim = RateLimiter(1, "bad")
    assert lim._path is not None
    lim._path.write_text("not json")
    await lim.acquire()
    assert len(json.loads(lim._path.read_text())) == 1


async def test_post_with_retry_acquires_limiter() -> None:
    from tether.providers.base import RateLimiter

    lim = RateLimiter(1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        resp = await post_with_retry(
            c, "http://x/y", provider="p", model="m", timeout=5, limiter=lim
        )
    assert resp.status_code == 200 and lim._claim() > 0
