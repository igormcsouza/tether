"""Tests for the background-job hint on a timed-out bash command (#319)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import Harness, SandboxPolicy
from tether.tools.bash import _has_background_job

TIMEOUT = "Error: command timed out after 30.0s (SIGKILL)."
HINT = (
    "A background job (`&`) keeps the command open. Instead: run it in the foreground with "
    "`timeout N <cmd>`, or send its output away: `<cmd> >/dev/null 2>&1 &`."
)


@pytest.mark.parametrize(
    ("cmd", "expected"),
    [
        ("bserver --port 8000 &", True),
        ("bserver &", True),
        ("bash server.sh & sleep 1", True),
        ("& ls", True),
        ("make 2>&1 &", True),
        ("a && b", False),
        ("a &&b", False),
        ("make 2>&1", False),
        ("make >&2", False),
        ("make &> out.log", False),
        ("echo 'a & b'", False),
        ('echo "x & y"', False),
        ('echo "a \\" & b"', False),
        ("echo \\& done", False),
        ("ls", False),
        ("", False),
    ],
)
def test_detects_an_unquoted_background_ampersand(cmd: str, expected: bool) -> None:
    assert _has_background_job(cmd) is expected


def _mux_with(tmp_path: Path, output: str, monkeypatch: pytest.MonkeyPatch):
    """A multiplexer whose sandbox returns `output` for every command (fake, no shell)."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)

    async def fake_execute(self: SandboxPolicy, cmd: str, stdin: str | None = None) -> str:
        return output

    monkeypatch.setattr(SandboxPolicy, "execute_bash", fake_execute)
    harness = Harness(db_path=tmp_path / "tether.db", tools=["bash"], sandbox=sandbox)
    return harness.build_multiplexer("ses_bg", ["bash"], sandbox, "ollama/qwen3.5:9b")


async def test_timeout_of_a_background_job_gets_the_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = (
        await _mux_with(tmp_path, TIMEOUT, monkeypatch).execute("bash bserver --port 8000 &")
    ).output
    assert out.splitlines()[0] == TIMEOUT
    assert HINT in out


async def test_timeout_of_a_background_script_from_stdin_gets_the_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = (
        await _mux_with(tmp_path, TIMEOUT, monkeypatch).execute("bash", stdin="bserver &")
    ).output
    assert HINT in out


async def test_hint_follows_a_skipped_cd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = (
        await _mux_with(tmp_path, TIMEOUT, monkeypatch).execute("bash cd /nope_319 && bserver &")
    ).output
    assert HINT in out


async def test_timeout_without_a_background_job_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = (await _mux_with(tmp_path, TIMEOUT, monkeypatch).execute("bash sleep 60")).output
    assert TIMEOUT in out
    assert HINT not in out


async def test_non_timeout_result_with_a_background_job_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = (await _mux_with(tmp_path, "started\n", monkeypatch).execute("bash bserver &")).output
    assert "started" in out
    assert HINT not in out
