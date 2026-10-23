"""Agent-to-agent interface: --json, exit codes, output schema, events, MCP server (#46)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from tether import ActionCall, ModelResponse, register_provider
from tether.cli import _async_main
from tether.schema import validate_output


class Script:
    """Replays a fixed list of actions (last repeats); an Exception entry is raised."""

    model_name = "x"

    def __init__(self, steps: list[Any]) -> None:
        self.steps = steps
        self.i = 0

    async def generate(self, messages: Any, tools: Any) -> ModelResponse:
        s = self.steps[min(self.i, len(self.steps) - 1)]
        self.i += 1
        if isinstance(s, Exception):
            raise s
        return ModelResponse(content="", action=s, prompt_tokens=10, completion_tokens=5)


def _reg(prefix: str, steps: list[Any]) -> str:
    script = Script(steps)
    register_provider(prefix, lambda name: script)
    return f"{prefix}/m"


async def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = await _async_main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


async def test_json_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "t.db")
    done = _reg("ai-ok", [ActionCall(cmd="done", stdin="hello")])
    code, out, _ = await _run(capsys, ["run", "--json", "--model", done, "--db", db, "g"])
    d = json.loads(out)
    assert code == 0 and d["status"] == "COMPLETED" and d["result"] == "hello"
    assert d["v"] == 1 and d["tokens"] == {"prompt": 10, "completion": 5} and d["failure"] is None

    ask = _reg("ai-ask", [ActionCall(cmd="done --ask", stdin="which db?")])
    code, out, _ = await _run(capsys, ["run", "--json", "--model", ask, "--db", db, "g"])
    d = json.loads(out)
    assert code == 2 and d["status"] == "WAITING_INPUT" and d["result"] == "which db?"

    loop = _reg("ai-loop", [ActionCall(cmd="mem list")])
    code, out, err = await _run(
        capsys, ["run", "--model", loop, "--db", db, "--max-steps", "2", "g"]
    )
    assert code == 4 and out == "" and "Max steps" in err  # failure text on stderr, not stdout

    code, out, _ = await _run(
        capsys, ["run", "--json", "--model", loop, "--db", db, "--max-steps", "2", "g"]
    )
    d = json.loads(out)
    assert d["failure"]["kind"] == "max_steps" and d["result"] is None

    boom = _reg("ai-boom", [AssertionError()])
    code, out, _ = await _run(capsys, ["run", "--json", "--model", boom, "--db", db, "g"])
    d = json.loads(out)
    assert code == 5 and d["failure"]["message"] == "Worker error: AssertionError"  # #41

    gate = _reg("ai-gate", [ActionCall(cmd="done", stdin="x")])
    code, out, _ = await _run(
        capsys, ["run", "--json", "--model", gate, "--db", db, "--verify", "false", "g"]
    )
    d = json.loads(out)
    assert code == 3 and d["failure"]["kind"] == "gate" and d["failure"]["gate"] == "false"


async def test_json_readers_result_file_and_events(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "t.db")
    rf = tmp_path / "out.txt"
    m = _reg("ai-rf", [ActionCall(cmd="done", stdin="deliverable")])
    code, out, _ = await _run(
        capsys, ["run", "--model", m, "--db", db, "--result-file", str(rf), "g"]
    )
    assert code == 0 and out == "" and rf.read_text() == "deliverable"

    _, out, _ = await _run(capsys, ["list", "--json", "--db", db])
    sid = json.loads(out)[0]["id"]
    for argv in (["status"], ["read"], ["read", "--digest"], ["wait"]):
        code, out, _ = await _run(capsys, [*argv, sid, "--json", "--db", db])
        assert code == 0 and json.loads(out)
    _, out, _ = await _run(capsys, ["stats", "--json", "--db", db])
    assert json.loads(out)["models"][0]["runs"] == 1
    code, out, _ = await _run(capsys, ["events", sid, "--follow", "--db", db])
    lines = [json.loads(x) for x in out.splitlines()]
    assert code == 0 and lines[-1] == {"event": "status", "status": "COMPLETED"}
    assert any(ev.get("cmd") == "done" for ev in lines)


async def test_output_schema_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "t.db")
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"type": "object", "required": ["n"]}))
    bad = _reg("ai-bad", [ActionCall(cmd="done", stdin="not json")])
    code, out, _ = await _run(
        capsys, ["run", "--json", "--model", bad, "--db", db, "--output-schema", str(schema), "g"]
    )
    assert code == 3 and json.loads(out)["failure"]["gate"] == "output-schema"
    good = _reg("ai-good", [ActionCall(cmd="done", stdin='{"n": 1}')])
    code, out, _ = await _run(
        capsys, ["run", "--json", "--model", good, "--db", db, "--output-schema", str(schema), "g"]
    )
    assert code == 0 and json.loads(out)["status"] == "COMPLETED"


def test_validate_output() -> None:
    sch = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "array", "items": {"type": "integer"}}},
    }
    assert validate_output('{"a": [1, 2]}', sch) is None
    assert validate_output('```json\n{"a": []}\n```', sch) is None
    assert "$.a[1]" in (validate_output('{"a": [1, "x"]}', sch) or "")
    assert "missing" in (validate_output("{}", sch) or "")
    assert validate_output("[]", sch) is not None


async def test_mcp_tools_run_and_ask_roundtrip(tmp_path: Path) -> None:
    import mcp

    from tether.mcp import build_server

    m = _reg(
        "ai-mcp",
        [ActionCall(cmd="done --ask", stdin="q?"), ActionCall(cmd="done", stdin="a")],
    )
    async with mcp.Client(build_server(tmp_path / "t.db", tmp_path)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert names >= {"tether_run", "tether_send", "tether_wait"}

        async def call(name: str, **args: Any) -> Any:
            res = await c.call_tool(name, args)
            return res.is_error, json.loads(res.content[0].text) if not res.is_error else (
                res.content[0].text
            )

        err, run = await call("tether_run", goal="g", model=m)
        assert not err and run["status"] == "WAITING_INPUT" and run["result"] == "q?"
        err, msg = await call("tether_status", id="ses_nope")
        assert err and "not found" in msg
        err, done = await call("tether_send", id=run["id"], message="pg", wait=True)
        assert not err and done["status"] == "COMPLETED" and done["result"] == "a"
        err, digests = await call("tether_wait", ids=[run["id"]], timeout=1)
        assert not err and digests[0]["status"] == "COMPLETED"


async def test_mcp_missing_extra_warns(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "tether.mcp", None)  # makes the import raise ImportError
    code, out, err = await _run(capsys, ["mcp"])
    assert code == 1 and out == "" and "tether-sdk[mcp]" in err


def test_validate_output_type_and_enum_errors() -> None:
    assert "expected integer" in (validate_output("true", {"type": "integer"}) or "")
    assert "not in" in (validate_output('"c"', {"enum": ["a", "b"]}) or "")


async def test_cli_events_send_read_json_and_mcp_serve(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from contextlib import asynccontextmanager

    import tether.mcp as mcp_mod
    from tether import Harness

    db = str(tmp_path / "t.db")
    m = _reg("ai-misc", [ActionCall(cmd="done", stdin="ok")])
    code, out, _ = await _run(capsys, ["run", "--json", "--model", m, "--db", db, "g"])
    sid = json.loads(out)["id"]

    # events: not found, plain (no --follow), and --follow on a session that finishes later
    assert (await _run(capsys, ["events", "ses_nope", "--db", db]))[0] == 1
    code, out, _ = await _run(capsys, ["events", sid, "--db", db])
    assert code == 0 and json.loads(out.splitlines()[0])["turn"] > 0
    h = Harness(db_path=db)
    h.store.update_session(sid, status="RUNNING", pid=os.getpid())

    async def finish() -> None:
        await asyncio.sleep(0.2)
        h.store.update_session(sid, status="COMPLETED")

    task = asyncio.create_task(finish())
    code, out, _ = await _run(capsys, ["events", sid, "--follow", "--db", db])
    await task
    assert json.loads(out.splitlines()[-1])["status"] == "COMPLETED"

    code, out, _ = await _run(capsys, ["read", sid, "--steps", "--json", "--db", db])
    assert isinstance(json.loads(out), list)
    code, out, _ = await _run(capsys, ["send", sid, "--json", "--db", db, "more"])
    assert json.loads(out)["id"] == sid

    # `tether mcp` wires workspace/db into serve()
    seen: dict[str, Any] = {}

    async def fake_serve(db_path: Any = None, workspace: Any = None) -> None:
        seen.update(db=db_path, ws=workspace)

    monkeypatch.setattr(mcp_mod, "serve", fake_serve)
    assert (await _run(capsys, ["mcp", "--db", db, "--workspace", str(tmp_path)]))[0] == 0
    assert seen["db"] == db and seen["ws"] == tmp_path

    # serve() runs the SDK server over stdio streams
    ran: list[Any] = []

    @asynccontextmanager
    async def fake_stdio() -> Any:
        yield "r", "w"

    async def fake_run(self: Any, r: Any, w: Any, opts: Any) -> None:
        ran.append((r, w))

    monkeypatch.undo()
    monkeypatch.setattr(mcp_mod, "stdio_server", fake_stdio)
    monkeypatch.setattr(mcp_mod.lowlevel.Server, "run", fake_run)
    await mcp_mod.serve(tmp_path / "s.db", tmp_path)
    assert ran == [("r", "w")]


async def test_mcp_remaining_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import mcp

    from tether.mcp import build_server

    monkeypatch.setattr(
        "tether.harness.subprocess.Popen", lambda *a, **kw: type("P", (), {"pid": 1})()
    )
    m = _reg("ai-tools", [ActionCall(cmd="done", stdin="alpha beta gamma")])
    async with mcp.Client(build_server(tmp_path / "t.db", tmp_path)) as c:

        async def call(name: str, **args: Any) -> tuple[bool, Any]:
            res = await c.call_tool(name, args)
            text = res.content[0].text  # type: ignore[union-attr]
            return bool(res.is_error), (text if res.is_error else json.loads(text))

        _, run = await call("tether_run", goal="g", model=m, output_schema=None)
        sid = run["id"]
        assert (await call("tether_read", id=sid, mode="steps"))[1]
        assert "digest" in (await call("tether_read", id=sid, mode="digest"))[1]
        assert (await call("tether_read", id=sid))[1]["result"] == "alpha beta gamma"
        assert (await call("tether_list", limit=5))[1][0]["id"] == sid
        assert (await call("tether_stats", model=m))[1]["models"]
        hits = (await call("tether_query", id=sid, query="alpha"))[1]
        assert hits and "alpha" in hits[0]["text"]
        # background send/run return immediately
        assert (await call("tether_send", id=sid, message="again"))[1]["id"] == sid
        err, bg = await call("tether_run", goal="g", model=m, wait=False)
        assert not err and bg["id"].startswith("ses_")
        # wait times out on a session that stays RUNNING
        from tether import Harness

        Harness(db_path=tmp_path / "t.db").store.update_session(sid, status="RUNNING")
        err, digests = await call("tether_wait", ids=[sid], timeout=0.3)
        assert digests[0]["status"] == "RUNNING"
        # errors: unknown session on send, unknown tool, bad args, bad Harness config
        assert (await call("tether_send", id="ses_nope", message="x"))[0]
        assert "unknown tool" in (await call("tether_nope"))[1]
        err, msg = await call("tether_read")
        assert err and "KeyError" in msg
        assert (await call("tether_run", goal="g", tools="definitely_not_a_tool"))[0]


async def test_mcp_run_accepts_params(tmp_path: Path) -> None:
    import mcp

    from tether.mcp import build_server
    from tether.store import SQLiteStore

    m = _reg("ai-mcp-params", [ActionCall(cmd="done", stdin="a")])
    db = tmp_path / "t.db"
    async with mcp.Client(build_server(db, tmp_path)) as c:
        res = await c.call_tool(
            "tether_run", {"goal": "g", "model": m, "params": {"temperature": 0}}
        )
        assert not res.is_error
    assert SQLiteStore(db).list_sessions()[0].sandbox_config["params"] == {"temperature": 0}


def test_stalled_and_stopped_failures_are_classified() -> None:
    from tether import api
    from tether.store import SessionRecord

    def rec(msg: str) -> SessionRecord:
        return SessionRecord(
            id="ses_x", parent_id=None, status="FAILED", model="m", skill=None, tools=[],
            sandbox_config={}, goal="g", result=msg, step_count=1, max_steps=2, peak_tokens=0,
            pid=None, created_at=0.0, updated_at=0.0,
        )  # fmt: skip

    stalled = api.failure_info(rec("Stalled: 4 loop warnings"))
    assert stalled and stalled["kind"] == "stalled"
    assert api.exit_code(rec("Stalled: x")) == api.EXIT_MAX_STEPS
    assert api.exit_code(rec("Stopped by user.")) == api.EXIT_ERROR
