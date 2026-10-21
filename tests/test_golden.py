"""Golden-trace replay: recorded model actions -> real harness -> exact-output snapshot.

Each `tests/golden/<name>.json` is a scripted session (workspace files, stubbed tools, model
steps, optional `send` phases). The harness, multiplexer, real `edit`/`done`/`mem` tools,
context assembly and folding all run for real; only the model and network tools are replaced.
The snapshot (`<name>.snap.json`) holds everything the model would have been shown plus the
final state, so any change in framing, folding, nudges, tool output or token estimates is a
visible diff. Intended change: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`, review the
diff. Record a real run into a fixture with `scripts/record_golden.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, SandboxPolicy, tool

GOLDEN = Path(__file__).parent / "golden"
FIXTURES = sorted(p for p in GOLDEN.glob("*.json") if not p.name.endswith(".snap.json"))


def _stub(name: str, outputs: list[str]) -> Any:
    it = iter(outputs)

    @tool(name=name, description=f"stub {name}")
    def stub(args: str = "") -> str:
        return next(it, "[stub exhausted]")

    return stub


def _steps(raw: list[dict[str, Any]]) -> list[ModelResponse]:
    return [
        ModelResponse(
            content=s.get("content", ""),
            action=ActionCall(cmd=s["cmd"], stdin=s.get("stdin")) if s.get("cmd") else None,
        )
        for s in raw
    ]


async def _replay(fx: dict[str, Any], ws: Path) -> dict[str, Any]:
    for rel, body in fx.get("files", {}).items():
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(body)
    tools: list[Any] = [*fx["tools"], *(_stub(n, o) for n, o in fx.get("stubs", {}).items())]
    sandbox = SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False)
    provider = FakeScriptedProvider([])
    harness = Harness(
        db_path=ws / ".t.db",
        tools=tools,
        sandbox=sandbox,
        provider=provider,
        max_steps=fx.get("max_steps", 15),
        verify=fx.get("verify"),
    )
    rec = harness.create_session(fx["goal"])
    for i, phase in enumerate(fx["phases"]):
        provider._responses.extend(_steps(phase["steps"]))
        rec = (
            await harness.execute_session(rec.id)
            if i == 0
            else await harness.send(rec.id, phase["send"])
        )
    turns = harness.store.get_turns(rec.id)
    snap = {
        "status": rec.status,
        "step_count": rec.step_count,
        "result": rec.result,
        "peak_tokens": rec.peak_tokens,
        "events": [t.event_type for t in turns if t.role == "assistant"],
        "calls": provider.recorded_calls,
        "files": {
            str(p.relative_to(ws)): p.read_text()
            for p in sorted(ws.rglob("*"))
            if p.is_file() and not p.name.startswith(".t.db")
        },
    }
    # normalise the temp workspace path so snapshots are machine independent
    return json.loads(json.dumps(snap).replace(str(ws), "<WS>"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
async def test_golden_trace(path: Path, tmp_path: Path) -> None:
    fx = json.loads(path.read_text())
    got = await _replay(fx, tmp_path)
    snap = path.with_suffix(".snap.json")
    if os.environ.get("UPDATE_GOLDEN") or not snap.exists():
        snap.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        if not os.environ.get("UPDATE_GOLDEN"):
            pytest.fail(f"{snap.name} did not exist; created it. Review and commit.")
        return
    assert got == json.loads(snap.read_text()), (
        f"{path.stem} drifted from its snapshot. If intended: UPDATE_GOLDEN=1 pytest "
        "tests/test_golden.py and review the diff."
    )
