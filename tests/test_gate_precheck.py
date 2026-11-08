"""#82: a misconfigured verify gate fails before any model call (acceptance tests)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.gates import precheck
from tether.sandbox import SandboxPolicy


def _policy(root: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)


def test_good_gates_pass(tmp_path: Path) -> None:
    (tmp_path / "check.sh").write_text("exit 0\n")
    gates = [
        "python3 -m pytest -q",
        "FOO=1 python3 -c 'print(1)'",
        "./check.sh",
        "cd sub && python3 -V",
    ]
    assert precheck(gates, _policy(tmp_path)) is None


def test_missing_program_is_named(tmp_path: Path) -> None:
    msg = precheck(["python3 -V", "no-such-tool-xyz --check"], _policy(tmp_path))
    assert msg is not None
    assert "no-such-tool-xyz" in msg and "not found" in msg


def test_unparsable_gate_is_reported(tmp_path: Path) -> None:
    msg = precheck(["python3 -c 'unterminated"], _policy(tmp_path))
    assert msg is not None and "parse" in msg


def test_empty_gate_is_reported(tmp_path: Path) -> None:
    msg = precheck(["   "], _policy(tmp_path))
    assert msg is not None and "empty" in msg


def test_missing_relative_script_is_reported(tmp_path: Path) -> None:
    msg = precheck(["./missing.sh"], _policy(tmp_path))
    assert msg is not None and "./missing.sh" in msg


async def test_session_fails_before_the_first_model_call(tmp_path: Path) -> None:
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd="done", stdin="x"))]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        provider=provider,
        verify=["no-such-tool-xyz"],
        max_steps=3,
        sandbox=_policy(tmp_path),
    )
    rec = await h.run("goal")
    assert rec.status == "FAILED"
    assert rec.step_count == 0
    assert "no-such-tool-xyz" in (rec.result or "") and "misconfigured" in (rec.result or "")
    assert provider.recorded_calls == []
    events = [t.event_type for t in h.store.get_turns(rec.id)]
    assert "gate_error" in events


async def test_good_gate_does_not_block_the_run(tmp_path: Path) -> None:
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd="done", stdin="x"))]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        provider=provider,
        verify=["python3 -c 'print(1)'"],
        max_steps=3,
        sandbox=_policy(tmp_path),
    )
    rec = await h.run("goal")
    assert rec.status == "COMPLETED"
