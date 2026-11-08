"""tether_run `workspace` argument: narrows the sandbox root inside the server workspace (#242)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from tests.conftest import FakeScriptedProvider  # noqa: E402
from tether.mcp import TetherMCP, ToolError  # noqa: E402
from tether.providers.base import ActionCall, ModelResponse  # noqa: E402


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "root"
    ws.mkdir()
    done = ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))
    monkeypatch.setattr(
        "tether.harness.resolve_provider",
        lambda *a, **k: FakeScriptedProvider([done]),
    )
    return ws


def _call(impl: TetherMCP, name: str, a: dict[str, Any]) -> Any:
    return asyncio.run(impl.call(name, a))


def _run_root(impl: TetherMCP, args: dict[str, Any]) -> str:
    out = _call(impl, "tether_run", {"goal": "g", "wait": False, **args})
    rec = impl.store.get_session(out["id"])
    assert rec is not None
    return str(rec.sandbox_config["workspace_root"])


def test_run_default_workspace_unchanged(tmp_path: Path, root: Path) -> None:
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    assert _run_root(impl, {}) == str(root.resolve())


def test_run_subdir_narrows_root(tmp_path: Path, root: Path) -> None:
    wt = root / "wt"
    wt.mkdir()
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    assert _run_root(impl, {"workspace": str(wt)}) == str(wt.resolve())


def test_run_rejects_outside_root(tmp_path: Path, root: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    with pytest.raises(ToolError) as info:
        _call(impl, "tether_run", {"goal": "g", "wait": False, "workspace": str(other)})
    assert "outside the server workspace" in str(info.value)
    assert str(root.resolve()) in str(info.value)
    assert impl.store.list_sessions() == []


def test_run_rejects_symlink_escape(tmp_path: Path, root: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    with pytest.raises(ToolError, match="outside the server workspace"):
        _call(impl, "tether_run", {"goal": "g", "wait": False, "workspace": str(root / "link")})
    assert impl.store.list_sessions() == []


def test_run_rejects_missing_or_relative(tmp_path: Path, root: Path) -> None:
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    for bad in ("nope", "rel/dir", str(root / "missing")):
        with pytest.raises(ToolError, match="must be an existing absolute directory"):
            _call(impl, "tether_run", {"goal": "g", "wait": False, "workspace": bad})
    assert impl.store.list_sessions() == []


def test_run_rejects_non_string_workspace(tmp_path: Path, root: Path) -> None:
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    for bad in (5, [str(root)]):
        with pytest.raises(ToolError, match="must be a string path"):
            _call(impl, "tether_run", {"goal": "g", "wait": False, "workspace": bad})
    assert impl.store.list_sessions() == []


def test_status_finds_worktree_run(tmp_path: Path, root: Path) -> None:
    wt = root / "wt"
    wt.mkdir()
    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=root)
    out = _call(impl, "tether_run", {"goal": "g", "wait": False, "workspace": str(wt)})
    result = _call(impl, "tether_status", {"id": out["id"]})
    assert result["id"] == out["id"]
