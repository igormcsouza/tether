"""MCP server over stdio (`tether mcp`), built on the optional official `mcp` SDK.

Install with `pip install 'tether-sdk[mcp]'`. Core Tether never imports this module.
Results are the same JSON as `--json`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import lowlevel
from mcp.server.stdio import stdio_server

from tether import __version__, api
from tether.harness import Harness
from tether.sandbox import SandboxPolicy
from tether.store import SQLiteStore

_ID = {"type": "string", "description": "Session id (ses_...)"}


def _tool(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": desc,
        "input_schema": {"type": "object", "properties": props, "required": required},
    }


TOOLS: list[dict[str, Any]] = [
    _tool(
        "tether_run",
        "Delegate a goal to a cheap/local model. wait=false returns the id at once.",
        {
            "goal": {"type": "string"},
            "model": {"type": "string", "description": "e.g. ollama/qwen3.5:9b"},
            "skill": {"type": "string"},
            "tools": {"type": "string", "description": "comma list, e.g. web,bash"},
            "verify": {"type": "array", "items": {"type": "string"}},
            "max_steps": {"type": "integer"},
            "sandbox": {"type": "string", "enum": ["workspace-write", "read-only"]},
            "no_network": {"type": "boolean"},
            "output_schema": {"type": "object", "description": "JSON Schema for the deliverable"},
            "wait": {"type": "boolean", "description": "default true"},
        },
        ["goal"],
    ),
    _tool("tether_status", "Session status, steps, tokens, failure kind.", {"id": _ID}, ["id"]),
    _tool(
        "tether_wait",
        "Block until sessions finish or need input; returns compact digests.",
        {"ids": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "number"}},
        ["ids"],
    ),
    _tool(
        "tether_read",
        "Read a session: full result (default), digest, or steps.",
        {"id": _ID, "mode": {"type": "string", "enum": ["full", "digest", "steps"]}},
        ["id"],
    ),
    _tool(
        "tether_send",
        "Answer a WAITING_INPUT session or give a follow-up. wait=true runs inline.",
        {"id": _ID, "message": {"type": "string"}, "wait": {"type": "boolean"}},
        ["id", "message"],
    ),
    _tool("tether_list", "Recent sessions.", {"limit": {"type": "integer"}}, []),
    _tool(
        "tether_stats",
        "Per-model pass rate, tokens, friction.",
        {"model": {"type": "string"}, "skill": {"type": "string"}},
        [],
    ),
    _tool(
        "tether_query",
        "BM25 snippets from a session's deliverable and observations.",
        {"id": _ID, "query": {"type": "string"}, "top": {"type": "integer"}},
        ["id", "query"],
    ),
]


class ToolError(Exception):
    pass


class TetherMCP:
    def __init__(self, db_path: str | Path | None, workspace: Path) -> None:
        self.db_path = db_path
        self.workspace = workspace.resolve()
        self.store = SQLiteStore(db_path=db_path)

    def _session(self, sid: str) -> Any:
        rec = self.store.get_session(sid)
        if rec is None:
            raise ToolError(f"session `{sid}` not found")
        return rec

    async def call(self, name: str, a: dict[str, Any]) -> Any:
        if name == "tether_run":
            return await self._run(a)
        if name == "tether_status":
            return api.session_dict(self._session(a["id"]), include_result=False)
        if name == "tether_wait":
            return await self._wait(a["ids"], float(a.get("timeout") or 120.0))
        if name == "tether_read":
            rec = self._session(a["id"])
            mode = a.get("mode") or "full"
            if mode == "steps":
                return api.events(self.store, rec.id)
            if mode == "digest":
                return api.digest_dict(self.store, rec)
            return api.session_dict(rec)
        if name == "tether_send":
            harness = Harness(db_path=self.db_path)
            try:
                rec = await harness.send(a["id"], a["message"], headless=not a.get("wait"))
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            return api.session_dict(rec)
        if name == "tether_list":
            recs = self.store.list_sessions(limit=int(a.get("limit") or 20))
            return [api.session_dict(r, include_result=False) for r in recs]
        if name == "tether_stats":
            return api.stats_dict(self.store, model=a.get("model"), skill=a.get("skill"), limit=100)
        if name == "tether_query":
            hits = self.store.search_chunks(
                a["query"], session_ids=[a["id"]], top_k=int(a.get("top") or 3)
            )
            return [
                {"source": f"{h.source_type}:{h.source_id}#{h.chunk_index}", "text": h.content}
                for h in hits
            ]
        raise ToolError(f"unknown tool `{name}`")

    async def _run(self, a: dict[str, Any]) -> Any:
        # Sandbox is always rooted at the server's workspace; callers can only narrow it.
        sandbox = SandboxPolicy(
            profile=a.get("sandbox") or "workspace-write",
            workspace_root=self.workspace,
            network=not a.get("no_network"),
        )
        try:
            harness = Harness(
                model=a.get("model"),
                skill=a.get("skill"),
                tools=a.get("tools"),
                verify=a.get("verify"),
                sandbox=sandbox,
                db_path=self.db_path,
                max_steps=int(a.get("max_steps") or 15),
                output_schema=a.get("output_schema"),
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if a.get("wait", True):
            return api.session_dict(await harness.run(a["goal"]))
        return {"v": api.SCHEMA_VERSION, "id": harness.spawn(a["goal"])}

    async def _wait(self, ids: list[str], timeout: float) -> Any:
        done = ("COMPLETED", "FAILED", "WAITING_INPUT")
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while True:
            recs = [self._session(i) for i in ids]
            if any(r.status == "WAITING_INPUT" for r in recs) or all(
                r.status in done for r in recs
            ):
                break
            if loop.time() >= end:
                break
            await asyncio.sleep(0.2)
        return [api.digest_dict(self.store, r) for r in recs]


def build_server(db_path: str | Path | None, workspace: Path) -> lowlevel.Server:
    impl = TetherMCP(db_path, workspace)

    async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[types.Tool(**t) for t in TOOLS])

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            data = await impl.call(params.name, params.arguments or {})
            text, err = json.dumps(data), False
        except ToolError as exc:
            text, err = str(exc), True
        except Exception as exc:  # provider/IO failure must not kill the server
            text, err = f"{type(exc).__name__}: {exc}", True
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)], is_error=err
        )

    return lowlevel.Server(
        "tether", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool
    )


async def serve(db_path: str | Path | None = None, workspace: Path | None = None) -> None:
    server = build_server(db_path, workspace or Path.cwd())
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
