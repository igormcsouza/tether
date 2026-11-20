"""bwrap installed but blocked is told apart from bwrap missing (#311)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

import tether.sandbox as sb
from tether import SandboxPolicy, doctor
from tether.cli import _async_main

BLOCKED_ERR = "bwrap: setting up uid map: Permission denied"


def _run_returning(rc: int, stderr: str) -> Any:
    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert kwargs.get("stderr") == subprocess.PIPE, "the probe must capture stderr"
        return subprocess.CompletedProcess(argv, rc, b"", stderr.encode())

    return run


def test_probe_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb.shutil, "which", lambda name: None)
    assert sb.bwrap_probe() == sb.BwrapProbe("missing", "", "")


def test_probe_blocked_keeps_the_last_stderr_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb.shutil, "which", lambda name: "/usr/bin/bwrap")
    monkeypatch.setattr(sb.subprocess, "run", _run_returning(1, f"noise\n{BLOCKED_ERR}\n"))
    assert sb.bwrap_probe() == sb.BwrapProbe("blocked", "/usr/bin/bwrap", BLOCKED_ERR)


def test_probe_blocked_when_it_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise subprocess.TimeoutExpired("bwrap", 2.0)

    monkeypatch.setattr(sb.shutil, "which", lambda name: "/usr/bin/bwrap")
    monkeypatch.setattr(sb.subprocess, "run", boom)
    probe = sb.bwrap_probe()
    assert probe.state == "blocked" and probe.path == "/usr/bin/bwrap" and probe.error


def test_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb.shutil, "which", lambda name: "/usr/bin/bwrap")
    monkeypatch.setattr(sb.subprocess, "run", _run_returning(0, ""))
    assert sb.bwrap_probe() == sb.BwrapProbe("ok", "/usr/bin/bwrap", "")


def test_can_use_bwrap_caches_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def probe() -> sb.BwrapProbe:
        calls.append(1)
        return sb.BwrapProbe("blocked", "/usr/bin/bwrap", BLOCKED_ERR)

    monkeypatch.setattr(sb, "_BWRAP_USABLE", None)
    monkeypatch.setattr(sb, "_BWRAP_PROBE", None)
    monkeypatch.setattr(sb, "bwrap_probe", probe)
    assert sb._can_use_bwrap() is False
    assert sb._can_use_bwrap() is False
    assert len(calls) == 1


def _policy(tmp_path: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=True)


def test_error_for_missing_bwrap_still_says_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TETHER_SANDBOX", "")
    monkeypatch.setattr(sb, "_BWRAP_USABLE", False)
    monkeypatch.setattr(sb, "_BWRAP_PROBE", sb.BwrapProbe("missing", "", ""))
    msg = _policy(tmp_path).isolation_error()
    assert msg is not None and "Install bubblewrap" in msg


def test_error_for_blocked_bwrap_does_not_say_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TETHER_SANDBOX", "")
    monkeypatch.setattr(sb, "_BWRAP_USABLE", False)
    monkeypatch.setattr(sb, "_BWRAP_PROBE", sb.BwrapProbe("blocked", "/usr/bin/bwrap", BLOCKED_ERR))
    msg = _policy(tmp_path).isolation_error()
    assert msg is not None
    assert "Install bubblewrap" not in msg and "install bubblewrap" not in msg
    assert BLOCKED_ERR in msg
    assert "apparmor_restrict_unprivileged_userns" in msg
    assert "TETHER_SANDBOX=container" in msg and "--allow-unsandboxed" in msg


def _checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: sb.BwrapProbe) -> Any:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x"))
    )
    monkeypatch.setattr(doctor, "bwrap_probe", lambda: probe)
    return {c.name: c for c in doctor.run_checks("openai/x", "http://h:1", tmp_path / "t.db")}


def test_doctor_blocked_bwrap_fails_with_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    by = _checks(tmp_path, monkeypatch, sb.BwrapProbe("blocked", "/usr/bin/bwrap", BLOCKED_ERR))
    check = by["bwrap"]
    assert not check.ok
    assert "/usr/bin/bwrap found but cannot create namespaces" in check.detail
    assert BLOCKED_ERR in check.detail
    assert "kernel.apparmor_restrict_unprivileged_userns=0" in check.detail
    assert "TETHER_SANDBOX=container" in check.detail and "--allow-unsandboxed" in check.detail


def test_doctor_missing_and_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    by = _checks(tmp_path, monkeypatch, sb.BwrapProbe("missing", "", ""))
    assert not by["bwrap"].ok and "install bubblewrap" in by["bwrap"].detail
    by = _checks(tmp_path, monkeypatch, sb.BwrapProbe("ok", "/usr/bin/bwrap", ""))
    assert by["bwrap"].ok and by["bwrap"].detail == "/usr/bin/bwrap"


async def test_cli_doctor_exits_1_when_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    monkeypatch.setattr(doctor, "bwrap_probe", lambda: sb.BwrapProbe("blocked", "/b", BLOCKED_ERR))
    code = await _async_main(["doctor", "--model", "openai/x", "--db", str(tmp_path / "t.db")])
    assert code == 1
    assert "FAIL bwrap" in capsys.readouterr().out
