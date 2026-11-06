"""Live progress on stderr for a foreground `tether run`: activity dots and `--verbose`."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import pytest

from tether import ActionCall, Harness, ModelResponse, SQLiteStore, register_provider
from tether.cli import _async_main
from tether.progress import dots_label, step_line, watch


def _session(tmp_path: Path) -> tuple[SQLiteStore, str]:
    db = tmp_path / "t.db"
    rec = Harness(db_path=db, model="ollama/m").create_session("goal")
    return SQLiteStore(db_path=db), rec.id


def _call(store: SQLiteStore, sid: str, step: int, cmd: str) -> None:
    store.add_turn(
        session_id=sid,
        step=step,
        role="assistant",
        content="",
        tool_cmd=cmd,
        prompt_tokens=800,
        completion_tokens=12,
        duration_ms=2100,
    )


def test_step_line_shows_step_command_time_and_tokens(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    _call(store, sid, 3, "edit view foo.py")
    assert step_line(store.get_turns(sid)[0]) == "[step 3] edit view foo.py (2.1s, 812 tok)"


def test_step_line_cuts_a_long_command_and_skips_non_calls(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    _call(store, sid, 1, "bash " + "x" * 300)
    store.add_turn(session_id=sid, step=1, role="tool", content="obs")
    calls, tool = store.get_turns(sid)
    assert len(step_line(calls) or "") < 120
    assert step_line(tool) is None


def test_dots_label_waits_for_the_model_then_names_the_last_step(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    assert dots_label("ollama/m", []) == "waiting for ollama/m"
    _call(store, sid, 2, "bash pytest -q")
    label = dots_label("ollama/m", store.get_turns(sid))
    assert "step 2" in label and "bash pytest -q" in label


async def _watching(store: SQLiteStore, sid: str, **kw: Any) -> tuple[io.StringIO, Any]:
    out = io.StringIO()
    task = asyncio.create_task(watch(store, sid, "ollama/m", stream=out, interval=0.01, **kw))
    await asyncio.sleep(0.08)
    return out, task


async def test_dots_animate_on_a_tty_and_clear_on_exit(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    out, task = await _watching(store, sid, verbose=False, tty=True)
    task.cancel()
    await task
    text = out.getvalue()
    assert "waiting for ollama/m" in text and "..." in text and "\n" not in text
    assert text.endswith("\r\033[K")


async def test_nothing_is_written_to_a_pipe_without_verbose(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    out, task = await _watching(store, sid, verbose=False, tty=False)
    _call(store, sid, 1, "done")
    await asyncio.sleep(0.05)
    task.cancel()
    await task
    assert out.getvalue() == ""


async def test_verbose_prints_each_step_once_and_the_last_one_on_exit(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    out, task = await _watching(store, sid, verbose=True, tty=False)
    _call(store, sid, 1, "edit view a.py")
    await asyncio.sleep(0.05)
    _call(store, sid, 2, "done")
    task.cancel()
    await task
    assert out.getvalue().splitlines() == [
        "[step 1] edit view a.py (2.1s, 812 tok)",
        "[step 2] done (2.1s, 812 tok)",
    ]


async def test_verbose_on_a_tty_erases_the_dots_before_each_line(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    out, task = await _watching(store, sid, verbose=True, tty=True)
    _call(store, sid, 1, "done")
    task.cancel()
    await task
    assert "\r\033[K[step 1] done" in out.getvalue()


class _Done:
    model_name = "m"

    async def generate(self, messages: Any, tools: Any) -> ModelResponse:
        return ModelResponse(content="", action=ActionCall(cmd="done", stdin="the answer"))


async def test_cli_verbose_goes_to_stderr_and_leaves_stdout_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    register_provider("prog-test", lambda name: _Done())
    argv = ["--model", "prog-test/m", "--db", str(tmp_path / "t.db")]
    assert await _async_main([*argv, "--verbose", "goal"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "the answer\n"
    assert "[step 1] done" in cap.err


async def test_cli_is_silent_by_default_when_stderr_is_not_a_tty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    register_provider("prog-test", lambda name: _Done())
    assert await _async_main(["--model", "prog-test/m", "--db", str(tmp_path / "t.db"), "g"]) == 0
    assert capsys.readouterr().err == ""


def test_dots_label_cuts_a_long_command(tmp_path: Path) -> None:
    store, sid = _session(tmp_path)
    _call(store, sid, 1, "bash " + "y" * 100)
    assert len(dots_label("ollama/m", store.get_turns(sid))) < 60
