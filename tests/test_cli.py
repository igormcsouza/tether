"""Unit tests for tether/cli.py (CLI subcommands: run, status, read, query, send, wait, list)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import tether.cli as cli_mod
from tether import ActionCall, Harness, ModelResponse, SQLiteStore, register_provider
from tether.cli import _async_main, main


async def test_cli_subcommands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify all CLI subcommands and options end-to-end."""
    monkeypatch.setattr(
        "tether.harness.subprocess.Popen",
        lambda *a, **kw: type("FakePopen", (), {"pid": 4242})(),
    )

    class QuickProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            return ModelResponse(
                content="", action=ActionCall(cmd="done", stdin="Final CLI output")
            )

    register_provider("cli-test", lambda name: QuickProvider())
    db_file = tmp_path / "tether.db"
    db_arg = str(db_file)
    store = SQLiteStore(db_path=db_file)
    h = Harness(db_path=db_file, model="cli-test/qwen", provider=QuickProvider())
    s_done = await h.run("Initial CLI session")

    assert await _async_main([]) == 0
    assert (
        await _async_main(["--model", "cli-test/qwen", "--db", db_arg, "Shorthand run goal"]) == 0
    )
    assert (
        await _async_main(
            ["run", "--headless", "--model", "cli-test/qwen", "--db", db_arg, "Headless goal"]
        )
        == 0
    )

    pipe_file = tmp_path / "cli_pipe.yaml"
    pipe_file.write_text(
        "name: cli-pipe\nstages:\n  - id: s1\n    model: cli-test/qwen\n    goal: '{{goal}}'\n",
        encoding="utf-8",
    )
    assert await _async_main(["pipeline", str(pipe_file), "--db", db_arg, "Run CLI pipeline"]) == 0
    assert (
        await _async_main(
            [
                "pipeline",
                str(pipe_file),
                "--headless",
                "--db",
                db_arg,
                "Run headless CLI pipeline",
            ]
        )
        == 0
    )

    assert await _async_main(["status", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["status", s_done.id, "--db", db_arg]) == 0

    assert await _async_main(["read", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["read", s_done.id, "--steps", "--db", db_arg]) == 0
    assert await _async_main(["read", s_done.id, "--digest", "--db", db_arg]) == 0
    assert await _async_main(["read", s_done.id, "--db", db_arg]) == 0
    capsys.readouterr()
    assert await _async_main(["read", s_done.id, "--db", db_arg]) == 0
    default_out = capsys.readouterr().out
    assert await _async_main(["read", s_done.id, "--full", "--db", db_arg]) == 0
    assert capsys.readouterr().out == default_out
    assert await _async_main(["read", s_done.id, "--digest", "--db", db_arg]) == 0
    assert capsys.readouterr().out != default_out
    with pytest.raises(SystemExit) as exc:
        await _async_main(["read", s_done.id, "--full", "--digest", "--db", db_arg])
    assert exc.value.code == 2
    assert await _async_main(["read", s_done.id, "--full", "--json", "--db", db_arg]) == 0
    assert await _async_main(["read", "ses_nope", "--full", "--db", db_arg]) == 1

    assert await _async_main(["query", s_done.id, "Final", "--db", db_arg]) == 0
    assert await _async_main(["query", s_done.id, "nonexistent_xyz", "--db", db_arg]) == 0

    assert await _async_main(["send", s_done.id, "--db", db_arg, "More work"]) == 0
    assert await _async_main(["send", s_done.id, "--headless", "--db", db_arg, "Headless msg"]) == 0
    assert await _async_main(["_worker", s_done.id, "--db", db_arg]) == 0

    s_wait = store.create_session("Wait session")

    async def _finish_soon() -> None:
        await asyncio.sleep(0.08)
        store.update_session(s_wait.id, status="COMPLETED", result="Done waiting")

    task = asyncio.create_task(_finish_soon())
    assert await _async_main(["wait", s_wait.id, "--timeout", "1.0", "--db", db_arg]) == 0
    await task

    assert await _async_main(["list", "--db", db_arg]) == 0
    assert await _async_main(["stats", "--db", db_arg]) == 0
    assert await _async_main(["stats", "--model", "cli-test/qwen", "--db", db_arg]) == 0
    empty_db = str(tmp_path / "empty.db")
    assert await _async_main(["list", "--db", empty_db]) == 0
    assert await _async_main(["stats", "--db", empty_db]) == 0

    orig_build_parser = cli_mod.build_parser

    class DummyParser:
        def parse_args(self, argv: Any) -> Any:
            return type("NS", (), {"subcommand": "unknown"})()

        def print_help(self) -> None:
            pass

    monkeypatch.setattr(cli_mod, "build_parser", lambda: DummyParser())
    assert await _async_main(["run"]) == 0
    monkeypatch.setattr(cli_mod, "build_parser", orig_build_parser)


def test_cli_sync_main_entrypoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test synchronous main() entrypoint with explicit argv and sys.argv."""
    empty_db = str(tmp_path / "empty_sync.db")
    main(["list", "--db", empty_db])
    monkeypatch.setattr("sys.argv", ["tether", "list", "--db", empty_db])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0


async def test_stop_terminates_a_running_worker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    db_arg = str(tmp_path / "tether.db")
    h = Harness(db_path=db_arg)
    rec = h.create_session("stuck")
    h.store.update_session(rec.id, status="RUNNING", pid=424242)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        cli_mod.os, "kill", lambda pid, sig: killed.append((pid, sig)) if sig else None
    )
    assert await _async_main(["stop", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["stop", rec.id, "--db", db_arg]) == 0
    assert killed == [(424242, cli_mod.signal.SIGTERM)]
    after = h.store.get_session(rec.id)
    assert after is not None and after.status == "FAILED"
    assert after.result == "Stopped by user."
    assert await _async_main(["stop", rec.id, "--json", "--db", db_arg]) == 0
    assert '"kind": "stopped"' in capsys.readouterr().out
    assert len(killed) == 1  # a finished session is left alone
