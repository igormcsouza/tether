"""Restart after repeated failing check runs: a fresh history that describes, never replays."""

from __future__ import annotations

import os
import time
from collections import Counter
from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.context import (
    RESTART_MAX_CHARS,
    after_restart,
    describe_attempts,
    modified_files,
    restart_message,
)
from tether.sandbox import SandboxPolicy
from tether.store import TurnRecord


def _turn(i: int, event: str = "ok", role: str = "assistant") -> TurnRecord:
    return TurnRecord(i, "s", i, role, f"t{i}", None, None, None, 0.0, event_type=event)


def test_after_restart_keeps_only_the_latest_restart_and_what_follows() -> None:
    turns = [_turn(1), _turn(2, "restart", "user"), _turn(3), _turn(4, "restart", "user"), _turn(5)]
    assert [t.id for t in after_restart(turns)] == [4, 5]
    plain = [_turn(1), _turn(2)]
    assert after_restart(plain) is plain


def test_modified_files_returns_only_files_written_during_the_session(tmp_path: Path) -> None:
    old = tmp_path / "test_x.py"
    old.write_text("old", encoding="utf-8")
    past = time.time() - 100
    os.utime(old, (past, past))
    (tmp_path / "x.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00")  # not text: skipped
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (tmp_path / ".tether").mkdir()
    (tmp_path / ".tether" / "db").write_text("secret", encoding="utf-8")
    assert modified_files(tmp_path, since=time.time() - 50) == {"x.py": "print(1)\n"}


def test_restart_message_describes_and_is_bounded() -> None:
    msg = restart_message(
        step=14,
        check_cmd="python3 -m unittest",
        failing_output="E" * 5000 + "\nFAILED (errors=3)\n[exit 1]",
        files={"bowling.py": "x = 1\n" * 3000},
        tried=["bowling.py changed 2 times", "bowling_test.py read 8 times"],
    )
    assert msg.startswith("[RESTART at step 14")
    assert "FAILED (errors=3)" in msg and "x = 1" in msg and "python3 -m unittest" in msg
    assert "bowling_test.py read 8 times" in msg
    assert len(msg) <= RESTART_MAX_CHARS


def test_describe_attempts_counts_without_quoting_commands() -> None:
    tried = describe_attempts(
        ["a.py", "b.py"],
        ["edit write a.py", "cat > a.py <<EOF"],
        Counter({"t.py": 8, "u.py": 1}),
        "pytest -q",
        3,
    )
    assert tried == [
        "a.py changed 2 times",
        "t.py read 8 times",
        "`pytest -q` run 3 times with a failing result each time",
    ]


def _script(cmds: list[tuple[str, str | None]]) -> list[ModelResponse]:
    steps = [ModelResponse(content="", action=ActionCall(cmd=c, stdin=s)) for c, s in cmds]
    return [*steps, ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))]


async def test_third_failing_check_after_edits_restarts_with_a_fresh_history(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "test_t.py").write_text(
        "import unittest\nimport a\n\n\nclass T(unittest.TestCase):\n"
        "    def test_x(self):\n        self.assertEqual(a.X, 2)\n",
        encoding="utf-8",
    )
    run = ("bash -c 'python3 -m unittest test_t 2>&1'", None)
    cmds = [
        ("edit write a.py", "X = 1  # MARKER_FIRST\n"),
        run,
        ("edit write a.py", "X = 3\n"),
        run,
        ("edit write a.py", "X = 4  # LATEST\n"),
        run,
        ("edit write a.py", "X = 5\n"),
        run,
        ("edit write a.py", "X = 6\n"),
        run,
    ]
    provider = FakeScriptedProvider(_script(cmds))
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=["edit", "bash"],
        sandbox=SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False),
        provider=provider,
        max_steps=20,
    )
    session = await harness.run("make the test pass")
    turns = harness.store.get_turns(session.id)
    restarts = [t for t in turns if t.event_type == "restart"]
    assert len(restarts) == 1  # capped at one per session
    body = restarts[0].content
    assert "X = 4  # LATEST" in body and "AssertionError" in body
    assert "a.py changed 3 times" in body
    assert "MARKER_FIRST" not in body
    # the call after the restart sees the restart message and none of the earlier steps
    after = "\n".join(str(m.get("content")) for m in provider.recorded_calls[6])
    assert "[RESTART at step 6" in after and "MARKER_FIRST" not in after
    # before it, the full history was still replayed
    before = "\n".join(str(m.get("content")) for m in provider.recorded_calls[5])
    assert "MARKER_FIRST" in before


async def test_a_check_that_keeps_failing_without_edits_does_not_restart(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "test_t.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
        "        self.fail('no')\n",
        encoding="utf-8",
    )
    run = ("bash -c 'python3 -m unittest test_t 2>&1'", None)
    provider = FakeScriptedProvider(_script([run, run, run, run]))
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=["bash"],
        sandbox=SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False),
        provider=provider,
        max_steps=20,
    )
    session = await harness.run("go")
    assert not [t for t in harness.store.get_turns(session.id) if t.event_type == "restart"]
