"""CommandProvider retries timeouts and empty failures (#268).

Each test runs real subprocesses: a fake command whose behaviour per attempt comes
from a plan. Backoff sleeps are recorded, never waited for.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

import tether.providers.declarative as declarative
from tether.providers.base import ProviderError
from tether.providers.declarative import CommandProvider

TIMEOUT = 0.3
MESSAGES = [{"role": "user", "content": "test"}]
TOOLS = [{"name": "test", "description": "test", "input_schema": {"type": "object"}}]

FAKE = r"""
import json, os, sys, time
counter, plan, pids = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
try:
    n = int(open(counter).read())
except FileNotFoundError:
    n = 0
open(counter, 'w').write(str(n + 1))
open(pids, 'a').write(str(os.getpid()) + ' ')
mode = plan[min(n, len(plan) - 1)]
sys.stdin.read()
if mode == 'hang':
    time.sleep(30)
elif mode == 'fail':
    sys.exit(1)
elif mode == 'fail_out':
    sys.stderr.write('boom')
    sys.exit(1)
elif mode == 'badjson':
    print('not json')
else:
    print(json.dumps({'cmd': 'echo hi', 'stdin': None}))
"""


class _AsyncioProxy:
    """Stands in for the asyncio name in declarative.py: sleep is recorded, the rest is real."""

    def __init__(self, sleeps: list[float]) -> None:
        self._sleeps = sleeps

    async def sleep(self, delay: float) -> None:
        self._sleeps.append(delay)

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(declarative, "asyncio", _AsyncioProxy(recorded))
    return recorded


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    (tmp_path / "fake.py").write_text(FAKE)
    return tmp_path


def _provider(run_dir: Path, plan: list[str]) -> CommandProvider:
    argv = [
        sys.executable,
        str(run_dir / "fake.py"),
        str(run_dir / "counter"),
        json.dumps(plan),
        str(run_dir / "pids"),
    ]
    return CommandProvider("test-model", argv=argv, reply="{conversation}", timeout=TIMEOUT)


def _spawns(run_dir: Path) -> int:
    counter = run_dir / "counter"
    return int(counter.read_text()) if counter.exists() else 0


async def _generate(provider: CommandProvider) -> Any:
    return await provider.generate(MESSAGES, TOOLS)


async def test_timeout_then_ok(run_dir: Path, sleeps: list[float]) -> None:
    """DoD-1: a timeout is retried and the second attempt's answer is returned."""
    response = await _generate(_provider(run_dir, ["hang", "ok"]))
    assert response is not None
    assert _spawns(run_dir) == 2
    assert sleeps == [1.0]


async def test_empty_failure_then_ok(run_dir: Path, sleeps: list[float]) -> None:
    """DoD-2: a non-zero exit with no output is retried the same way."""
    response = await _generate(_provider(run_dir, ["fail", "ok"]))
    assert response is not None
    assert _spawns(run_dir) == 2
    assert sleeps == [1.0]


async def test_gives_up_with_provider_error(run_dir: Path, sleeps: list[float]) -> None:
    """DoD-3: three timeouts raise ProviderError naming the model and the timeout."""
    with pytest.raises(ProviderError) as info:
        await _generate(_provider(run_dir, ["hang"]))
    message = str(info.value)
    assert "test-model" in message
    assert "timeout 0.3s" in message
    assert "command" in message
    assert _spawns(run_dir) == 3
    assert sleeps == [1.0, 2.0]
    # each timed-out process is killed and reaped, so its pid no longer exists
    pids = (run_dir / "pids").read_text().split()
    assert len(pids) == 3
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)


async def test_gives_up_on_empty_failures(run_dir: Path, sleeps: list[float]) -> None:
    """Empty failure on all three attempts raises ProviderError with the exit code."""
    with pytest.raises(ProviderError, match="exited 1"):
        await _generate(_provider(run_dir, ["fail"]))
    assert _spawns(run_dir) == 3
    assert sleeps == [1.0, 2.0]


async def test_timeout_then_empty_failure_then_ok(run_dir: Path, sleeps: list[float]) -> None:
    """Mixed retryable failures share one attempt budget."""
    response = await _generate(_provider(run_dir, ["hang", "fail", "ok"]))
    assert response is not None
    assert _spawns(run_dir) == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize("plan", [["fail_out"], ["badjson"]])
async def test_no_retry_when_output_present(
    run_dir: Path, sleeps: list[float], plan: list[str]
) -> None:
    """DoD-4: a non-zero exit with output, or an unparsable reply, fails at once."""
    with pytest.raises(RuntimeError):
        await _generate(_provider(run_dir, plan))
    assert _spawns(run_dir) == 1
    assert sleeps == []


async def test_missing_binary_is_not_retried(run_dir: Path, sleeps: list[float]) -> None:
    """A missing executable is a setup error, not a transient failure."""
    provider = CommandProvider(
        "test-model",
        argv=[str(run_dir / "no-such-binary")],
        reply="{conversation}",
        timeout=TIMEOUT,
    )
    with pytest.raises(FileNotFoundError):
        await _generate(provider)
    assert sleeps == []
