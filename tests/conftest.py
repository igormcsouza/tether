"""Shared test helpers and fixtures for Tether unit & integration tests."""

from __future__ import annotations

from typing import Any

from tether.providers.base import ActionCall, ModelResponse


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
