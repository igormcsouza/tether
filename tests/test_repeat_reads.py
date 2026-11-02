"""#199 point a repeated live read at the earlier output; #136 escalate loops."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, tool
from tether.sandbox import SandboxPolicy


def _script(cmds: list[str]) -> list[ModelResponse]:
    steps = [ModelResponse(content="", action=ActionCall(cmd=c), prompt_tokens=10) for c in cmds]
    return [*steps, ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))]


async def _run(tmp_path: Path, cmds: list[str]) -> tuple[Harness, FakeScriptedProvider, str]:
    ws = tmp_path / "ws"
    ws.mkdir()
    for name in "abc":
        (ws / f"{name}.py").write_text(f"X = '{name}'\n", encoding="utf-8")
    provider = FakeScriptedProvider(_script(cmds))
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=["edit"],
        sandbox=SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False),
        provider=provider,
    )
    session = await harness.run("goal")
    return harness, provider, session.id


def _prompt(provider: FakeScriptedProvider, call: int) -> str:
    return "\n".join(str(m.get("content")) for m in provider.recorded_calls[call])


def _executed_views(harness: Harness, sid: str) -> int:
    return sum(1 for t in harness.store.get_turns(sid) if t.obs_id)


async def test_repeat_read_of_unchanged_live_file_is_not_re_run(tmp_path: Path) -> None:
    harness, provider, sid = await _run(
        tmp_path, ["edit view a.py", "edit view b.py", "edit view a.py"]
    )
    assert _executed_views(harness, sid) == 2  # a, b; the third read ran nothing
    first = next(t.obs_id for t in harness.store.get_turns(sid) if t.obs_id)
    note = _prompt(provider, 3)
    assert "unchanged" in note and str(first) in note


async def test_the_pointer_is_given_once_then_the_read_runs(tmp_path: Path) -> None:
    cmds = [
        "edit view a.py",
        "edit view b.py",
        "edit view a.py",
        "edit view c.py",
        "edit view a.py",
    ]
    harness, _, sid = await _run(tmp_path, cmds)
    assert _executed_views(harness, sid) == 4  # a, b, c, then a again for real


async def test_an_edit_makes_the_file_readable_again(tmp_path: Path) -> None:
    cmds = ["edit view a.py", "edit write a.py", "edit view b.py", "edit view a.py"]
    harness, _, sid = await _run(tmp_path, cmds)
    assert _executed_views(harness, sid) == 4  # the edit invalidated a.py: the last read runs


async def test_escalated_loop_message_from_the_second_repeat(tmp_path: Path) -> None:
    @tool(name="ping", description="Ping a host")
    def ping(host: str) -> str:
        return f"pong {host}"

    provider = FakeScriptedProvider(_script(["ping x"] * 4))
    harness = Harness(db_path=tmp_path / "tether.db", tools=[ping], provider=provider)
    await harness.run("goal")
    assert "Do not repeat the same command" in _prompt(provider, 2)
    assert "already have this output above" not in _prompt(provider, 2)
    assert "already have this output above" in _prompt(provider, 3)
