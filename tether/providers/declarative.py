"""Declarative providers loaded from ~/.tether/providers.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from tether.providers.anthropic import AnthropicProvider
from tether.providers.base import ModelProvider
from tether.providers.ollama import OllamaProvider
from tether.providers.openai import OpenAIProvider

VALID_KINDS = ("openai", "ollama", "anthropic")
BUILTIN_PREFIXES = ("ollama", "openai", "anthropic")


def providers_path() -> Path:
    """Return the providers file path (TETHER_PROVIDERS overrides the default)."""
    env = os.environ.get("TETHER_PROVIDERS")
    if env:
        return Path(env)
    return Path.home() / ".tether" / "providers.yaml"


def load_declared() -> dict[str, dict[str, Any]]:
    """Load and validate declared providers; returns {} if the file is missing."""
    path = providers_path()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("providers.yaml: top level must be a mapping of name -> mapping")
    result: dict[str, dict[str, Any]] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"providers.yaml: entry `{name}` must be a mapping")
        if str(name).lower() in BUILTIN_PREFIXES:
            raise ValueError(f"providers.yaml: `{name}` cannot shadow a built-in provider")
        kind = cfg.get("kind")
        if kind == "command":
            raise ValueError("kind `command` not supported yet")
        if kind not in VALID_KINDS:
            raise ValueError(
                f"providers.yaml: entry `{name}` has unknown kind `{kind}`. "
                f"Valid kinds: {', '.join(VALID_KINDS)}."
            )
        result[str(name)] = cfg
    return result


def build_declared(cfg: dict[str, Any], model_name: str, *, num_ctx: int) -> ModelProvider:
    """Build a provider instance from a declared config entry."""
    kind = cfg["kind"]
    api_key_env = cfg.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if kind == "openai":
        return OpenAIProvider(model_name, api_key=api_key, base_url=cfg.get("base_url"))
    if kind == "ollama":
        return OllamaProvider(model_name, host=cfg.get("host"), num_ctx=num_ctx)
    return AnthropicProvider(model_name, api_key=api_key, base_url=cfg.get("base_url"))
