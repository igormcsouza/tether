"""`tether doctor`: checks the setup and says what to fix (acceptance tests, written first)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from tether import doctor
from tether.cli import _async_main


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


def test_all_checks_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    monkeypatch.setattr(httpx, "get", _tags(["qwen3.5:9b"]))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    checks = doctor.run_checks("ollama/qwen3.5:9b", "http://h:1", tmp_path / "t.db")
    by = _by_name(checks)
    assert set(by) == {"ollama", "model", "bwrap", "providers", "db"}
    assert all(c.ok for c in checks), checks


def test_ollama_down_says_how_to_fix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", _down)
    by = _by_name(doctor.run_checks("ollama/qwen3.5:9b", "http://h:1", tmp_path / "t.db"))
    assert not by["ollama"].ok and "http://h:1" in by["ollama"].detail
    assert "OLLAMA_HOST" in by["ollama"].detail
    assert not by["model"].ok  # cannot be checked when the server is down


def test_model_not_pulled_names_the_pull_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(httpx, "get", _tags(["llama3:8b"]))
    by = _by_name(doctor.run_checks("ollama/qwen3.5:9b", "http://h:1", tmp_path / "t.db"))
    assert by["ollama"].ok
    assert not by["model"].ok and "ollama pull qwen3.5:9b" in by["model"].detail


def test_non_ollama_model_skips_the_ollama_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(httpx, "get", _down)
    by = _by_name(doctor.run_checks("openai/gpt-4o-mini", "http://h:1", tmp_path / "t.db"))
    assert "ollama" not in by and "model" not in by


def test_missing_bwrap_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", _tags(["qwen3.5:9b"]))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    by = _by_name(doctor.run_checks("ollama/qwen3.5:9b", "http://h:1", tmp_path / "t.db"))
    assert not by["bwrap"].ok and "bubblewrap" in by["bwrap"].detail


def test_invalid_providers_yaml_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "providers.yaml"
    bad.write_text("x: [unclosed\n")
    monkeypatch.setenv("TETHER_PROVIDERS", str(bad))
    monkeypatch.setattr(httpx, "get", _tags(["qwen3.5:9b"]))
    by = _by_name(doctor.run_checks("ollama/qwen3.5:9b", "http://h:1", tmp_path / "t.db"))
    assert not by["providers"].ok and "providers.yaml" in by["providers"].detail


def test_unopenable_db_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", _tags(["qwen3.5:9b"]))
    blocker = tmp_path / "file"
    blocker.write_text("not a dir")
    by = _by_name(doctor.run_checks("ollama/qwen3.5:9b", "http://h:1", blocker / "t.db"))
    assert not by["db"].ok


async def test_cli_exit_code_and_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    monkeypatch.setattr(httpx, "get", _tags(["qwen3.5:9b"]))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    db = str(tmp_path / "t.db")
    assert await _async_main(["doctor", "--model", "ollama/qwen3.5:9b", "--db", db]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any(ln.startswith("ok") and "ollama" in ln for ln in lines)
    assert any(ln.startswith("ok") and "bwrap" in ln for ln in lines)
    monkeypatch.setattr(httpx, "get", _down)
    assert await _async_main(["doctor", "--model", "ollama/qwen3.5:9b", "--db", db]) == 1
    assert "FAIL" in capsys.readouterr().out
