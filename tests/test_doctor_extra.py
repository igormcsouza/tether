"""Additional tests for tether doctor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from tether import doctor


class _Resp:
    def __init__(self, models: list[str]) -> None:
        self._models = models

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {"models": [{"name": m} for m in self._models]}


def _tags(models: list[str]) -> Any:
    def get(url: str, **_: Any) -> _Resp:
        assert url.endswith("/api/tags")
        return _Resp(models)

    return get


def _down(url: str, **_: Any) -> _Resp:
    raise httpx.ConnectError("refused")


def _by_name(checks: list[doctor.Check]) -> dict[str, doctor.Check]:
    return {c.name: c for c in checks}


def test_model_without_tag_is_ok_with_latest_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model without a tag (e.g. qwen3.5) is listed by Ollama as qwen3.5:latest."""
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    monkeypatch.setattr(httpx, "get", _tags(["qwen3.5:latest"]))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    checks = doctor.run_checks("ollama/qwen3.5", "http://h:1", tmp_path / "t.db")
    by = _by_name(checks)
    assert by["model"].ok, f"model check failed: {by['model']}"


def test_host_without_protocol_prefixes_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If host has no ://, prefix http:// before building the URL."""
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))

    called_urls: list[str] = []

    def track_get(url: str, **kwargs: Any) -> _Resp:
        called_urls.append(url)
        return _Resp(["qwen3.5:latest"])

    monkeypatch.setattr(httpx, "get", track_get)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    doctor.run_checks("ollama/qwen3.5", "h:1", tmp_path / "t.db")
    assert len(called_urls) == 1
    assert called_urls[0].startswith("http://h:1/")
