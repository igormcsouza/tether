from __future__ import annotations

from pathlib import Path

import pytest

from tether.providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    resolve_provider,
)
from tether.providers.declarative import build_declared, load_declared, providers_path


def _write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> Path:
    path = tmp_path / "p.yaml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("TETHER_PROVIDERS", str(path))
    return path


def test_providers_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "x.yaml"))
    assert providers_path() == tmp_path / "x.yaml"


def test_providers_path_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TETHER_PROVIDERS", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert providers_path() == tmp_path / ".tether" / "providers.yaml"


def test_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "nope.yaml"))
    assert load_declared() == {}


def test_empty_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "")
    assert load_declared() == {}


def test_top_level_not_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "- a\n- b\n")
    with pytest.raises(ValueError, match="providers.yaml"):
        load_declared()


def test_entry_not_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo: bar\n")
    with pytest.raises(ValueError, match="providers.yaml"):
        load_declared()


def test_command_kind_unsupported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo:\n  kind: command\n")
    with pytest.raises(ValueError, match="not supported yet"):
        load_declared()


def test_unknown_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo:\n  kind: bogus\n")
    with pytest.raises(ValueError, match="openai, ollama, anthropic"):
        load_declared()


def test_missing_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(monkeypatch, tmp_path, "foo:\n  base_url: http://x\n")
    with pytest.raises(ValueError, match="unknown kind"):
        load_declared()


@pytest.mark.parametrize("name", ["ollama", "openai", "anthropic"])
def test_cannot_shadow_builtins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> None:
    _write(monkeypatch, tmp_path, f"{name}:\n  kind: openai\n")
    with pytest.raises(ValueError, match="shadow"):
        load_declared()


def test_build_openai_with_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret")
    cfg = {"kind": "openai", "base_url": "http://x/v1", "api_key_env": "MY_KEY"}
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, OpenAIProvider)
    assert provider.api_key == "secret"
    assert provider.base_url.startswith("http://x/v1")


def test_build_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = {"kind": "ollama", "host": "http://h:11434"}
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, OllamaProvider)


def test_build_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A_KEY", "ak")
    cfg = {"kind": "anthropic", "api_key_env": "A_KEY", "base_url": "http://a"}
    provider = build_declared(cfg, "m", num_ctx=1024)
    assert isinstance(provider, AnthropicProvider)
    assert provider.api_key == "ak"


def test_resolve_provider_declared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(
        monkeypatch,
        tmp_path,
        "mygroq:\n  kind: openai\n  base_url: http://groq.local/v1\n",
    )
    provider = resolve_provider("mygroq/llama")
    assert isinstance(provider, OpenAIProvider)
    assert provider.model_name == "llama"
    assert provider.base_url.startswith("http://groq.local/v1")


def test_resolve_provider_unknown_still_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write(monkeypatch, tmp_path, "mygroq:\n  kind: openai\n")
    with pytest.raises(ValueError, match="Unknown model provider"):
        resolve_provider("other/llama")
