"""Usage limits surface the provider's own text and are not retried (#305).

Real subprocesses (tmp_path scripts) for the command provider; a fake provider for the
harness outage loop. Backoff sleeps are recorded, never waited for.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

import tether.harness as harness_mod
import tether.providers.declarative as declarative
from tether.harness import OUTAGE_RETRIES, Harness
from tether.providers.base import ProviderError
from tether.providers.declarative import CommandProvider

MESSAGES = [{"role": "user", "content": "test"}]
TOOLS = [{"name": "test", "description": "test", "input_schema": {"type": "object"}}]
LIMIT_JSON = '{"is_error": true, "result": "Claude usage limit reached. Resets 1:30pm"}'
LIMIT_TEXT = "Claude usage limit reached. Resets 1:30pm"

# argv: counter file, stdout text, stderr text. Always exits 1, records each call.
EMIT = r"""
import sys
sys.stdin.read()
with open(sys.argv[1], 'a') as f:
    f.write('call\n')
if sys.argv[2]:
    print(sys.argv[2])
if sys.argv[3]:
    sys.stderr.write(sys.argv[3])
sys.exit(1)
"""

# First attempt fails silently (retryable); later attempts print the limit JSON.
SILENT_THEN_LIMIT = r"""
import sys
sys.stdin.read()
counter = sys.argv[1]
try:
    n = int(open(counter).read())
except FileNotFoundError:
    n = 0
open(counter, 'w').write(str(n + 1))
if n == 0:
    sys.exit(1)
print(sys.argv[2])
sys.exit(1)
"""


class _AsyncioProxy:
    """Stands in for the asyncio name: sleep is recorded, everything else is real."""

    def __init__(self, sleeps: list[float]) -> None:
        self._sleeps = sleeps

    async def sleep(self, delay: float) -> None:
        self._sleeps.append(delay)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio_real, name)


import asyncio as asyncio_real  # noqa: E402


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(declarative, "asyncio", _AsyncioProxy(recorded))
    return recorded


def _count(path: Path) -> int:
    return len(path.read_text().splitlines()) if path.exists() else 0


def _emit_provider(tmp_path: Path, stdout: str, stderr: str = "") -> tuple[CommandProvider, Path]:
    script = tmp_path / "emit.py"
    script.write_text(EMIT)
    counter = tmp_path / "calls.txt"
    provider = CommandProvider(
        "test-model",
        argv=[sys.executable, str(script), str(counter), stdout, stderr],
        reply="result",
        timeout=5,
    )
    return provider, counter


async def _call(provider: CommandProvider) -> object:
    return await provider.generate(MESSAGES, TOOLS)


# DoD-1: retryable attribute on ProviderError


def test_provider_error_retryable_defaults_true() -> None:
    assert ProviderError("x").retryable is True


def test_provider_error_retryable_can_be_false() -> None:
    assert ProviderError("x", retryable=False).retryable is False


def test_provider_error_stays_runtime_error() -> None:
    assert isinstance(ProviderError("x", retryable=False), RuntimeError)


# DoD-2: non-zero exit with output is a single, non-retryable ProviderError


async def test_usage_limit_fails_once_with_provider_text(
    tmp_path: Path, sleeps: list[float]
) -> None:
    provider, counter = _emit_provider(tmp_path, LIMIT_JSON)
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    msg = str(info.value)
    assert "usage limit reached" in msg
    assert "--model" in msg
    assert "test-model" in msg
    assert "exit 1" in msg
    assert info.value.retryable is False
    assert _count(counter) == 1
    assert sleeps == []


async def test_stderr_only_output_is_used_as_provider_text(
    tmp_path: Path, sleeps: list[float]
) -> None:
    provider, counter = _emit_provider(tmp_path, "", stderr="quota exceeded, try later")
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    assert "quota exceeded, try later" in str(info.value)
    assert info.value.retryable is False
    assert _count(counter) == 1
    assert sleeps == []


async def test_json_without_reply_path_uses_raw_output(tmp_path: Path, sleeps: list[float]) -> None:
    provider, counter = _emit_provider(tmp_path, '{"other": 1}')
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    assert '"other"' in str(info.value)
    assert info.value.retryable is False
    assert _count(counter) == 1


async def test_provider_text_is_truncated_to_300_chars(tmp_path: Path, sleeps: list[float]) -> None:
    provider, counter = _emit_provider(tmp_path, "x" * 400)
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    msg = str(info.value)
    assert "x" * 300 in msg
    assert "x" * 301 not in msg
    assert _count(counter) == 1


async def test_limit_after_silent_failure_is_not_retried(
    tmp_path: Path, sleeps: list[float]
) -> None:
    script = tmp_path / "silent_then_limit.py"
    script.write_text(SILENT_THEN_LIMIT)
    counter = tmp_path / "calls.txt"
    provider = CommandProvider(
        "test-model",
        argv=[sys.executable, str(script), str(counter), LIMIT_JSON],
        reply="result",
        timeout=5,
    )
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    assert LIMIT_TEXT in str(info.value)
    assert info.value.retryable is False
    assert int(counter.read_text()) == 2
    # one backoff before the second attempt, none after the limit
    assert sleeps == [1.0]


# DoD-4: the harness outage loop re-raises at once when not retryable


class _FailingProvider:
    structured_history = False

    def __init__(self, *, retryable: bool) -> None:
        self.retryable = retryable
        self.calls = 0

    async def generate(self, messages: Any, tools: Any) -> Any:
        self.calls += 1
        raise ProviderError(
            f"command provider `test-model` failed (exit 1): {LIMIT_TEXT}",
            retryable=self.retryable,
        )


@pytest.fixture
def harness_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(harness_mod, "asyncio", _AsyncioProxy(recorded))
    return recorded


async def test_harness_stops_at_once_on_non_retryable_error(
    tmp_path: Path, harness_sleeps: list[float]
) -> None:
    provider = _FailingProvider(retryable=False)
    harness = Harness(db_path=tmp_path / "tether.db", provider=provider)
    rec = harness.create_session("goal")
    session = await harness.execute_session(rec.id)
    assert provider.calls == 1
    assert session.status == "FAILED"
    assert LIMIT_TEXT in (session.result or "")
    assert harness_sleeps == []


async def test_harness_still_retries_retryable_error(
    tmp_path: Path, harness_sleeps: list[float]
) -> None:
    provider = _FailingProvider(retryable=True)
    harness = Harness(db_path=tmp_path / "tether.db", provider=provider)
    rec = harness.create_session("goal")
    session = await harness.execute_session(rec.id)
    assert provider.calls == 1 + OUTAGE_RETRIES
    assert session.status == "FAILED"
    assert len(harness_sleeps) == OUTAGE_RETRIES


async def test_limit_message_is_exact(tmp_path: Path) -> None:
    provider, _ = _emit_provider(tmp_path, LIMIT_JSON)
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    assert str(info.value) == (
        f"command provider `test-model` failed (exit 1): {LIMIT_TEXT}. "
        "If this is a usage or rate limit, wait for the reset or pass another --model."
    )


async def test_non_string_reply_value_uses_raw_output(tmp_path: Path, sleeps: list[float]) -> None:
    provider, counter = _emit_provider(tmp_path, '{"result": 5}')
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    assert '{"result": 5}' in str(info.value)
    assert info.value.retryable is False
    assert _count(counter) == 1


async def test_stdout_wins_over_stderr(tmp_path: Path, sleeps: list[float]) -> None:
    provider, counter = _emit_provider(tmp_path, "plain stdout words", "stderr words")
    with pytest.raises(ProviderError) as info:
        await _call(provider)
    assert "plain stdout words" in str(info.value)
    assert "stderr words" not in str(info.value)
    assert info.value.retryable is False
    assert _count(counter) == 1
