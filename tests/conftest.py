"""Shared test helpers and fixtures for Tether unit & integration tests."""

from __future__ import annotations

from typing import Any

import pytest

from tether.providers.base import ActionCall, ModelResponse


@pytest.fixture(autouse=True)
def _container_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write-session tests must pass on hosts without bwrap: the test env acts as a container."""
    monkeypatch.setenv("TETHER_SANDBOX", "container")


@pytest.fixture
def no_landlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A kernel without Landlock: with bwrap also gone, a write session has no jail at all."""
    from tether import landlock

    monkeypatch.setattr(landlock, "abi", lambda: 0)


@pytest.fixture(autouse=True)
def _fresh_bwrap_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """A probe cached by an earlier test must not colour the refusal text of a later one (#311)."""
    import tether.sandbox as sandbox

    monkeypatch.setattr(sandbox, "_BWRAP_PROBE", None)


class FakeScriptedProvider:
    """Deterministic scripted provider for testing the Harness loop."""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.model_name = "fake/qwen3.5:9b"
        self._responses = list(responses)
        self.recorded_calls: list[list[dict[str, Any]]] = []

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        self.recorded_calls.append(list(messages))
        if not self._responses:
            return ModelResponse(
                content="Finishing up",
                action=ActionCall(cmd="done", stdin="Default completion"),
            )
        return self._responses.pop(0)
