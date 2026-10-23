"""Configurable context budget and fold window (#54)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tether import ActionCall, Harness, ModelResponse, register_provider
from tether.cli import _async_main
from tether.providers.declarative import load_declared


def _yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> None:
    p = tmp_path / "p.yaml"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setenv("TETHER_PROVIDERS", str(p))


ENTRY = "decl:\n  kind: openai\n  base_url: http://x\n  api_key_env: K\n"


def test_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    h = Harness(model="decl/m", db_path=db)
    assert (h.max_context_tokens, h.fold_observations_after) == (8192, 2)
    _yaml(monkeypatch, tmp_path, ENTRY + "  context_tokens: 32000\n  fold_after: 8\n")
    h = Harness(model="decl/m", db_path=db)
    assert (h.max_context_tokens, h.fold_observations_after) == (32000, 8)
    h = Harness(model="decl/m", db_path=db, max_context_tokens=100, fold_observations_after=5)
    assert (h.max_context_tokens, h.fold_observations_after) == (100, 5)
    _yaml(monkeypatch, tmp_path, "decl:\n  kind: nope\n")
    h = Harness(model="decl/m", db_path=db)
    assert h.max_context_tokens == 8192


@pytest.mark.parametrize("key", ["context_tokens", "fold_after", "rpm"])
@pytest.mark.parametrize("bad", ["0", "-1", "true", "'8'", "1.5"])
def test_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str, bad: str) -> None:
    _yaml(monkeypatch, tmp_path, ENTRY + f"  {key}: {bad}\n")
    with pytest.raises(ValueError, match=f"entry `decl` has invalid `{key}` "):
        load_declared()


class _P:
    model_name = "x"

    async def generate(self, messages: Any, tools: Any) -> ModelResponse:
        return ModelResponse(
            content="",
            action=ActionCall(cmd="done", stdin="ok"),
            prompt_tokens=1,
            completion_tokens=1,
        )


async def test_cli_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[Harness] = []

    class Rec(Harness):
        def __init__(self, *a: Any, **kw: Any) -> None:
            super().__init__(*a, **kw)
            seen.append(self)

    monkeypatch.setattr("tether.cli.Harness", Rec)
    register_provider("ctxcfg", lambda name: _P())
    db = str(tmp_path / "t.db")
    flags = ["--context-tokens", "123", "--fold-after", "7", "--db", db, "--model", "ctxcfg/m"]
    assert await _async_main(["run", "--json", *flags, "g"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETED"
    await _async_main(["pipeline", *flags, str(tmp_path / "missing.yaml"), "g"])
    assert len(seen) == 2
    assert all((h.max_context_tokens, h.fold_observations_after) == (123, 7) for h in seen)


async def test_mcp_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mcp

    from tether.mcp import build_server

    seen: list[Harness] = []

    class Rec(Harness):
        def __init__(self, *a: Any, **kw: Any) -> None:
            super().__init__(*a, **kw)
            seen.append(self)

    monkeypatch.setattr("tether.mcp.Harness", Rec)
    register_provider("ctxmcp", lambda name: _P())
    async with mcp.Client(build_server(tmp_path / "t.db", tmp_path)) as c:
        res = await c.call_tool(
            "tether_run",
            {"goal": "g", "model": "ctxmcp/m", "context_tokens": 50, "fold_after": 4},
        )
        assert not res.is_error
    assert (seen[0].max_context_tokens, seen[0].fold_observations_after) == (50, 4)
