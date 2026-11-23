"""`tether models` lists what tether can use (#310)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

import tether.models as models_mod
from tether.cli import _async_main
from tether.models import collect, render


class _Resp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {"models": [{"name": "qwen3.5:9b"}, {"name": "gemma4:e4b"}]}


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "providers.yaml"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sekret-value")
    monkeypatch.setenv("OLLAMA_HOST", "box:11434")
    monkeypatch.setattr(models_mod, "_CUSTOM_PROVIDERS", {})  # other tests register providers


def _ollama_up(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def get(url: str, timeout: float) -> _Resp:
        seen.append(url)
        return _Resp()

    monkeypatch.setattr(httpx, "get", get)
    return seen


def _ollama_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url: str, timeout: float) -> _Resp:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", get)


async def test_no_config_lists_pulled_models_and_builtins(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _ollama_up(monkeypatch)
    assert await _async_main(["models"]) == 0
    out = capsys.readouterr().out
    assert seen == ["http://box:11434/api/tags"]
    assert "ollama (http://box:11434)\n  ollama/qwen3.5:9b\n  ollama/gemma4:e4b" in out
    assert "providers.yaml" not in out and "registered" not in out
    assert "  openai/<model>  OPENAI_API_KEY: not set" in out
    assert "  anthropic/<model>  ANTHROPIC_API_KEY: set" in out
    assert "  ollama/<model>  default: ollama/qwen3.5:9b" in out
    assert "sekret-value" not in out


async def test_providers_yaml_and_registered_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ollama_up(monkeypatch)
    (tmp_path / "providers.yaml").write_text(
        "gw:\n  kind: openai\n  base_url: http://x/v1\n  api_key_env: GW_KEY\n"
        "local:\n  kind: ollama\n  host: http://y\n"
    )
    models_mod._CUSTOM_PROVIDERS["models-test"] = lambda name: None  # type: ignore[assignment,return-value]
    assert await _async_main(["models", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["v"] == 1
    assert data["ollama"]["models"] == ["ollama/qwen3.5:9b", "ollama/gemma4:e4b"]
    assert data["providers"] == [
        {"prefix": "gw", "kind": "openai", "key_env": "GW_KEY", "key_set": False},
        {"prefix": "local", "kind": "ollama"},
    ]
    assert "models-test" in data["registered"]
    text = render(data)
    assert "  gw/<model>  kind=openai  GW_KEY: not set" in text
    assert "registered\n" in text and "  models-test/<model>" in text


async def test_unreachable_ollama_is_one_line_and_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ollama_down(monkeypatch)
    assert await _async_main(["models"]) == 0
    out = capsys.readouterr().out
    assert "  not reachable: start Ollama or set OLLAMA_HOST" in out
    assert "built-in" in out


def test_no_pulled_models_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    _ollama_up(monkeypatch)
    data = collect("http://h")
    data["ollama"]["models"] = []
    assert "(no models pulled: ollama pull <model>)" in render(data)


async def test_invalid_providers_yaml_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ollama_up(monkeypatch)
    (tmp_path / "providers.yaml").write_text("bad:\n  kind: nope\n")
    assert await _async_main(["models"]) == 1
    assert "providers.yaml: entry `bad` has unknown kind" in capsys.readouterr().err
