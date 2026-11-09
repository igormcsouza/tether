"""tether_run `limits` argument reaches SandboxPolicy; bad values are a ToolError (#124 item 6)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

import tether.mcp as mcp_mod  # noqa: E402
from tether.mcp import TOOLS, TetherMCP, ToolError  # noqa: E402


def test_schema_has_limits() -> None:
    run = next(t for t in TOOLS if t["name"] == "tether_run")
    prop = run["input_schema"]["properties"]["limits"]
    assert prop["type"] == "object"
    assert prop["additionalProperties"]["type"] == "integer"


@pytest.mark.skipif(sys.platform != "linux", reason="limits need Linux")
def test_limits_pass_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    real = mcp_mod.SandboxPolicy

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(*args, **kwargs)

    class StopHere(Exception):
        pass

    def no_harness(*args: Any, **kwargs: Any) -> None:
        seen["sandbox"] = kwargs["sandbox"]
        raise StopHere

    monkeypatch.setattr(mcp_mod, "SandboxPolicy", spy)
    monkeypatch.setattr(mcp_mod, "Harness", no_harness)
    impl = TetherMCP(tmp_path / "db.sqlite", tmp_path)
    with pytest.raises(StopHere):
        asyncio.run(impl.call("tether_run", {"goal": "g", "limits": {"cpu": 60, "mem": 2048}}))
    assert seen["limits"] == {"cpu": 60, "mem": 2048}
    assert seen["sandbox"].limits == {"cpu": 60, "mem": 2048}


@pytest.mark.parametrize("bad", [{"nope": 1}, {"cpu": 1.0}, {"cpu": 10**30}])
def test_bad_limits_raise_tool_error(tmp_path: Path, bad: dict[str, Any]) -> None:
    impl = TetherMCP(tmp_path / "db.sqlite", tmp_path)
    with pytest.raises(ToolError, match="limit"):
        asyncio.run(impl.call("tether_run", {"goal": "g", "limits": bad}))
