"""Agent-to-agent interface: --json, exit codes, output schema, events, MCP server (#46)."""

from __future__ import annotations

import json
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
