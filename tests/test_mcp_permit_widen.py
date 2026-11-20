"""A shared MCP server refuses `allow` and `allow_unsandboxed` without --permit-widen (#306)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from tests.conftest import FakeScriptedProvider  # noqa: E402
from tether import cli  # noqa: E402
from tether.mcp import TetherMCP, ToolError, build_server  # noqa: E402
from tether.providers.base import ActionCall, ModelResponse  # noqa: E402


@pytest.fixture
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    done = ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))
    monkeypatch.setattr(
        "tether.harness.resolve_provider", lambda *a, **k: FakeScriptedProvider([done])
    )
    return root


def _run(impl: TetherMCP, **extra: Any) -> Any:
    return asyncio.run(impl.call("tether_run", {"goal": "g", "wait": False, **extra}))


@pytest.mark.parametrize("arg", [{"allow": ["git push"]}, {"allow_unsandboxed": True}])
def test_default_server_refuses_widening(tmp_path: Path, ws: Path, arg: dict[str, Any]) -> None:
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=ws)
    with pytest.raises(ToolError, match="--permit-widen"):
        _run(impl, **arg)


@pytest.mark.parametrize("arg", [{}, {"allow": []}, {"allow_unsandboxed": False}])
def test_default_server_still_runs_without_widening(
    tmp_path: Path, ws: Path, arg: dict[str, Any]
) -> None:
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=ws)
    assert _run(impl, **arg)["id"].startswith("ses_")


def test_permit_widen_allows_both(tmp_path: Path, ws: Path) -> None:
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=ws, permit_widen=True)
    out = _run(impl, allow=["git push"], allow_unsandboxed=True)
    rec = impl.store.get_session(out["id"])
    assert rec is not None
    assert rec.sandbox_config["allow_outside"] == ["git push"]
    assert rec.sandbox_config["allow_unsandboxed"] is True


def test_build_server_takes_permit_widen(tmp_path: Path, ws: Path) -> None:
    assert build_server(tmp_path / "t.db", ws, permit_widen=True) is not None


@pytest.mark.parametrize("flag,expected", [([], False), (["--permit-widen"], True)])
async def test_cli_flag_reaches_serve(
    monkeypatch: pytest.MonkeyPatch, flag: list[str], expected: bool
) -> None:
    seen: dict[str, Any] = {}

    async def fake_serve(**kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr("tether.mcp.serve", fake_serve)
    assert await cli._async_main(["mcp", *flag]) == 0
    assert seen["permit_widen"] is expected
