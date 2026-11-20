"""A --verify gate gets its own, longer timeout and says when it ran out (#304)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import Harness, SandboxPolicy


def _harness(tmp_path: Path, timeout_seconds: float) -> tuple[Harness, SandboxPolicy]:
    sandbox = SandboxPolicy(
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
        allow_unsandboxed=True,
        timeout_seconds=timeout_seconds,
    )
    h = Harness(
        model="ollama/x",
        sandbox=sandbox,
        db_path=tmp_path / "t.db",
        provider=FakeScriptedProvider([]),
    )
    return h, sandbox


async def test_gate_outlives_the_command_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_GATE_TIMEOUT", raising=False)
    h, sandbox = _harness(tmp_path, timeout_seconds=1)
    assert await h._run_verification_gates(sandbox, ["sleep 2 && echo ok"]) is None


async def test_gate_timeout_names_the_knob(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TETHER_GATE_TIMEOUT", "1")
    h, sandbox = _harness(tmp_path, timeout_seconds=30)
    failure = await h._run_verification_gates(sandbox, ["sleep 3"])
    assert failure is not None
    cmd, code, out, is_error = failure
    assert (cmd, code, is_error) == ("sleep 3", 124, True)
    assert "timed out after 1s" in out
    assert "TETHER_GATE_TIMEOUT" in out


async def test_a_gate_that_exits_124_itself_is_not_called_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_GATE_TIMEOUT", raising=False)
    h, sandbox = _harness(tmp_path, timeout_seconds=30)
    failure = await h._run_verification_gates(sandbox, ["exit 124"])
    assert failure is not None
    assert "timed out" not in failure[2]


async def test_bad_env_value_falls_back_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TETHER_GATE_TIMEOUT", "soon")
    h, sandbox = _harness(tmp_path, timeout_seconds=1)
    assert await h._run_verification_gates(sandbox, ["sleep 2 && echo ok"]) is None
