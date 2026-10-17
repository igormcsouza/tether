"""Unit tests for tether/sandbox.py (workspace jail, env scrubbing, bwrap, command guards)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy, SandboxViolationError


async def test_deterministic_security_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 6: Verify workspace path jail, sensitive file block, and env scrubbing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-key-12345")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-999")

    sandbox = SandboxPolicy(
        profile="workspace-write",
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
    )

    with pytest.raises(SandboxViolationError, match="outside workspace"):
        sandbox.resolve_safe_path("../outside.txt", write=True)

    for forbidden in (
        ".env",
        ".env.local",
        ".git/config",
        ".git/hooks/pre-commit",
        ".tether/tether.db",
    ):
        with pytest.raises(SandboxViolationError, match="protected path"):
            sandbox.resolve_safe_path(forbidden, write=False)

    for bad_cmd in ("sudo ls", "rm -rf /", "cat .env", "ls ../", "chmod 777 file.txt"):
        with pytest.raises(SandboxViolationError):
            await sandbox.execute_bash(bad_cmd)

    env_out = await sandbox.execute_bash("env")
    assert "sk-super-secret-key-12345" not in env_out
    assert "aws-secret-999" not in env_out

    ro_parent = SandboxPolicy(profile="read-only", workspace_root=tmp_path)
    child_policy = ro_parent.attenuate("workspace-write")
    assert child_policy.profile == "read-only"
    with pytest.raises(SandboxViolationError, match="read-only"):
        child_policy.resolve_safe_path("notes.txt", write=True)


async def test_sandbox_bwrap_and_execution_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover bwrap detection, read-only command validation, timeouts, and process group cleanup."""
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", None)
    monkeypatch.setattr(sb_mod.shutil, "which", lambda _: None)
    assert sb_mod._can_use_bwrap() is False
    assert sb_mod._can_use_bwrap() is False

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", None)
    monkeypatch.setattr(sb_mod.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setattr(
        sb_mod.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0),
    )
    assert sb_mod._can_use_bwrap() is True

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", None)

    def _raise_subproc(*a: Any, **kw: Any) -> Any:
        raise OSError("no bwrap")

    monkeypatch.setattr(sb_mod.subprocess, "run", _raise_subproc)
    assert sb_mod._can_use_bwrap() is False

    with pytest.raises(ValueError, match="Unsupported sandbox profile"):
        SandboxPolicy(profile="invalid")

    assert SandboxPolicy.from_dict(None).profile == "workspace-write"
    ro = SandboxPolicy(profile="read-only", workspace_root=tmp_path, use_kernel_sandbox=False)
    with pytest.raises(SandboxViolationError, match="Empty command"):
        ro.validate_bash_command("   ")
    with pytest.raises(SandboxViolationError, match="outside workspace"):
        ro.validate_bash_command("ls /etc/passwd")
    with pytest.raises(SandboxViolationError, match="mutating shell"):
        ro.validate_bash_command("echo hi > out.txt")
    with pytest.raises(SandboxViolationError, match="allowlist"):
        ro.validate_bash_command("python3 -c 'print(1)'")
    ro.validate_bash_command("echo 'unclosed")

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    ws_sb = SandboxPolicy(
        profile="workspace-write",
        workspace_root=tmp_path,
        use_kernel_sandbox=True,
        timeout_seconds=0.1,
        max_output_chars=40,
    )
    assert ws_sb._build_exec_argv("ls")[0] == "bwrap"
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", False)

    out_err = await ws_sb.execute_bash("echo err_msg >&2; exit 2")
    assert "[stderr]" in out_err and "[exit 2]" in out_err
    out_empty = await ws_sb.execute_bash("true")
    assert out_empty == "[exit 0]"
    out_trunc = await ws_sb.execute_bash("python3 -c 'print(\"X\" * 200)'")
    assert "truncated" in out_trunc
    out_timeout = await ws_sb.execute_bash("sleep 5")
    assert "timed out" in out_timeout

    def _raise_proc_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(sb_mod.os, "killpg", _raise_proc_lookup)
    sb_timeout = SandboxPolicy(
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
        timeout_seconds=0.05,
    )
    res_to = await sb_timeout.execute_bash("python3 -c 'import time; time.sleep(0.12)'")
    assert "timed out" in res_to
