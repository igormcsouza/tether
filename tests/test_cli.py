"""Unit tests for tether/cli.py (CLI subcommands: run, status, read, query, send, wait, list)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import tether.cli as cli_mod
from tether import ActionCall, Harness, ModelResponse, SQLiteStore, register_provider
from tether.cli import _async_main, main


async def test_cli_subcommands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert await _async_main(["status", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["status", s_done.id, "--db", db_arg]) == 0

    assert await _async_main(["read", "ses_nope", "--db", db_arg]) == 1
    assert await _async_main(["read", s_done.id, "--steps", "--db", db_arg]) == 0
    assert await _async_main(["read", s_done.id, "--digest", "--db", db_arg]) == 0
    assert await _async_main(["read", s_done.id, "--db", db_arg]) == 0

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
    empty_db = str(tmp_path / "empty.db")
    assert await _async_main(["list", "--db", empty_db]) == 0

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
