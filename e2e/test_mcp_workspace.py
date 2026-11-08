"""tether_run `workspace` over MCP stdio: narrows the sandbox inside the server workspace
and refuses anything outside it. Scripted: the proxy plays the model; MCP and tether are real."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest

from e2e.conftest import Tether

pytest.importorskip("mcp")


def _call(tether: Tether, args: dict[str, Any]) -> Any:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go() -> Any:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tether.cli", "mcp", "--workspace", str(tether.ws)],
            env=tether.env,
            cwd=str(tether.ws),
        )
        async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
            await s.initialize()
            return await s.call_tool("tether_run", {"goal": "go", "model": "e2e/scripted", **args})

    return asyncio.run(asyncio.wait_for(go(), 60))


def test_workspace_narrows_the_sandbox_to_a_subdir(tether: Tether, chaos) -> None:
    (tether.ws / "sub").mkdir()
    chaos.script("edit write f.txt <<'EOF'\nhi\nEOF", ("done", "ok"))
    res = _call(tether, {"workspace": str(tether.ws / "sub"), "tools": "edit"})
    run = json.loads(res.content[0].text)
    assert (run["status"], run["result"]) == ("COMPLETED", "ok"), run
    assert (tether.ws / "sub" / "f.txt").read_text() == "hi"
    assert not (tether.ws / "f.txt").exists(), "the write must land in sub, not the server root"


def test_workspace_outside_the_server_root_is_refused(tether: Tether, chaos, tmp_path) -> None:
    chaos.script(("done", "should not run"))
    res = _call(tether, {"workspace": str(tmp_path)})
    assert res.is_error, res
    assert "outside the server workspace" in res.content[0].text
    assert chaos.requests == [], "a refused workspace must never reach the model"


def test_relative_workspace_is_refused(tether: Tether, chaos) -> None:
    chaos.script(("done", "should not run"))
    res = _call(tether, {"workspace": "sub"})
    assert res.is_error, res
    assert "must be an existing absolute directory" in res.content[0].text
    assert chaos.requests == []
