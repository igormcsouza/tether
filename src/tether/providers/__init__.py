"""Model provider resolver for Tether (`ollama`, `openai`, `anthropic`)."""

from __future__ import annotations

from tether.providers.anthropic import AnthropicProvider
from tether.providers.base import ActionCall, ModelProvider, ModelResponse
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider


def resolve_provider(model: str, *, num_ctx: int = 8192) -> ModelProvider:
    """Resolve `<provider>/<model_name>` into an async ModelProvider instance."""
    spec = model.strip() or "ollama/qwen3.5:9b"
    if "/" in spec:
        prefix, name = spec.split("/", 1)
    else:
        prefix, name = "ollama", spec

    provider = prefix.lower()
    if provider == "ollama":
        return OllamaProvider(model_name=name, num_ctx=num_ctx)
    if provider in ("openai", "openrouter", "vllm", "groq", "deepseek"):
        return OpenAIProvider(model_name=name)
    if provider in ("anthropic", "claude"):
        return AnthropicProvider(model_name=name)
    raise ValueError(
        f"Unknown model provider `{prefix}` in `{model}`. "
        "Supported prefixes: `ollama/`, `openai/`, `anthropic/`."
    )


__all__ = [
    "ActionCall",
    "AnthropicProvider",
    "ModelProvider",
    "ModelResponse",
    "OllamaProvider",
    "OpenAIProvider",
    "resolve_provider",
]
