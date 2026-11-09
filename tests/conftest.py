"""Shared test helpers and fixtures for Tether unit & integration tests."""

from __future__ import annotations

from typing import Any

import pytest

from tether.providers.base import ActionCall, ModelResponse


@pytest.fixture(autouse=True)
def _container_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write-session tests must pass on hosts without bwrap: the test env acts as a container."""
    monkeypatch.setenv("TETHER_SANDBOX", "container")


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
