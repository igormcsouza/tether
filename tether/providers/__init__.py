"""Model provider resolver and custom SDK provider registry for Tether."""

from __future__ import annotations

from collections.abc import Callable

from tether.providers.anthropic import AnthropicProvider
from tether.providers.base import (
    ActionCall,
    ModelProvider,
    ModelResponse,
    ProviderResponse,
    extract_fallback_action,
    parse_tool_arguments,
)
from tether.providers.declarative import build_declared, load_declared
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider

ProviderFactory = Callable[[str], ModelProvider]
_CUSTOM_PROVIDERS: dict[str, ProviderFactory] = {}


def register_provider(prefix: str, factory: ProviderFactory) -> None:
    """Register a custom SDK model provider under `<prefix>/<model_name>`."""
    clean = prefix.strip().lower().rstrip("/")
    if not clean:
        raise ValueError("Provider prefix cannot be empty.")
    _CUSTOM_PROVIDERS[clean] = factory


def resolve_provider(model: str, *, num_ctx: int = 8192) -> ModelProvider:
    """Resolve `<provider>/<model_name>` into an async ModelProvider instance."""
    spec = model.strip() or "ollama/qwen3.5:9b"
    if "/" in spec:
        prefix, name = spec.split("/", 1)
    else:
        prefix, name = "ollama", spec

    provider = prefix.lower()
    if provider in _CUSTOM_PROVIDERS:
        return _CUSTOM_PROVIDERS[provider](name)
    if provider == "ollama":
        return OllamaProvider(model_name=name, num_ctx=num_ctx)
    if provider in ("openai", "openrouter", "vllm", "groq", "deepseek"):
        return OpenAIProvider(model_name=name)
    if provider in ("anthropic", "claude"):
        return AnthropicProvider(model_name=name)
    declared = load_declared()
    if provider in declared:
        return build_declared(declared[provider], name, num_ctx=num_ctx)
    supported = ["ollama/", "openai/", "anthropic/", *[f"{k}/" for k in _CUSTOM_PROVIDERS]]
    raise ValueError(
        f"Unknown model provider `{prefix}` in `{model}`. "
        f"Supported prefixes: {', '.join(supported)}."
    )


__all__ = [
    "ActionCall",
    "AnthropicProvider",
    "ModelProvider",
    "ModelResponse",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderFactory",
    "ProviderResponse",
    "extract_fallback_action",
    "parse_tool_arguments",
    "register_provider",
    "resolve_provider",
]
