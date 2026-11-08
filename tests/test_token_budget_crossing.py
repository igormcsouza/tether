"""Review fix: the call that crosses --max-tokens still runs and records its action."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy


def _resp(cmd: str, stdin: str | None = None) -> ModelResponse:
    return ModelResponse(
        content="",
        action=ActionCall(cmd=cmd, stdin=stdin),
        prompt_tokens=6,
        completion_tokens=6,
    )


def _harness(tmp_path: Path, provider: FakeScriptedProvider) -> Harness:
    return Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=provider,
        max_tokens=10,
        max_steps=5,
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )


async def test_done_on_the_crossing_call_completes(tmp_path: Path) -> None:
    h = _harness(tmp_path, FakeScriptedProvider([_resp("done", "finished")]))
    rec = await h.run("g")
    assert rec.status == "COMPLETED"
    assert rec.result == "finished"


async def test_action_on_the_crossing_call_runs_and_is_recorded(tmp_path: Path) -> None:
    provider = FakeScriptedProvider([_resp("echo crossed"), _resp("done", "late")])
    h = _harness(tmp_path, provider)
    rec = await h.run("g")
    assert rec.status == "WAITING_INPUT"
    assert "[TOKEN BUDGET]" in (rec.result or "")
    turns = h.store.get_turns(rec.id)
    assert any(t.role == "assistant" and t.tool_cmd == "echo crossed" for t in turns)
    assert any(t.role == "tool" and "crossed" in t.content for t in turns)
    assert len(provider.recorded_calls) == 1  # paused before the second model call
