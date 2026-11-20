"""Ctrl+C stops a run cleanly: one line, exit 130, session handed back, child killed (#309)."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import Harness, SandboxPolicy, api
from tether.cli import _async_main, main
from tether.providers.base import ModelResponse


class _Stall(FakeScriptedProvider):
    """A provider whose reply never comes."""

    async def generate(self, messages, tools):  # type: ignore[no-untyped-def]
        await asyncio.sleep(60)
        return ModelResponse(content="never")


def _policy(tmp_path: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False, allow_unsandboxed=True)


def test_exit_code_is_documented() -> None:
    assert api.EXIT_INTERRUPTED == 130
    assert "130" in Path("docs/reference/agent-interface.md").read_text()


async def test_cancelled_session_is_handed_back_not_left_running(tmp_path: Path) -> None:
    h = Harness(
        model="ollama/x", sandbox=_policy(tmp_path), db_path=tmp_path / "t.db", provider=_Stall([])
    )
    rec = h.create_session("goal")
    task = asyncio.create_task(h.execute_session(rec.id))
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    after = h.store.get_session(rec.id)
    assert after is not None
    assert after.status == "WAITING_INPUT"
    assert "interrupted" in (after.result or "").lower()


async def test_cancelled_bash_kills_its_child(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    marker = tmp_path / "pid"
    task = asyncio.create_task(policy.execute_bash_with_code(f"echo $$ > {marker}; sleep 60"))
    for _ in range(50):
        if marker.exists() and marker.read_text().strip():
            break
        await asyncio.sleep(0.1)
    pid = int(marker.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_run_prints_one_line_and_returns_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def cancelled(self: Harness, sid: str) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(Harness, "execute_session", cancelled)
    code = await _async_main(
        ["run", "--model", "ollama/x", "--allow-unsandboxed", "--db", str(tmp_path / "t.db"), "g"]
    )
    err = capsys.readouterr().err
    assert code == 130
    assert "Traceback" not in err
    last = err.strip().splitlines()[-1]
    assert last.startswith("interrupted; session ses_") and "tether send ses_" in last


def test_main_turns_keyboard_interrupt_into_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def boom(argv: list[str]) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("tether.cli._async_main", boom)
    assert main(["status", "ses_x"]) == 130
    err = capsys.readouterr().err
    assert "Traceback" not in err and "interrupted" in err


@pytest.mark.skipif(sys.platform != "linux", reason="SIGINT delivery")
def test_real_sigint_during_a_stalled_model_call(tmp_path: Path) -> None:
    import http.server
    import threading

    class Stall(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            time.sleep(30)

        def log_message(self, *a: object) -> None:
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stall)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {**os.environ, "OLLAMA_HOST": f"http://127.0.0.1:{srv.server_port}"}
    env.pop("TETHER_SANDBOX", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "tether.cli", "run", "--model", "ollama/x", "--allow-unsandboxed",
         "--db", str(tmp_path / "t.db"), "say hi"],
        cwd=tmp_path, env=env, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip
    time.sleep(3)
    proc.send_signal(signal.SIGINT)
    _, err = proc.communicate(timeout=20)
    srv.shutdown()
    assert proc.returncode == 130, err
    assert "Traceback" not in err, err
    assert "interrupted; session ses_" in err
