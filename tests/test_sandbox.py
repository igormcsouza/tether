"""Unit tests for tether/sandbox.py (workspace jail, env scrubbing, bwrap, command guards)."""

from __future__ import annotations

import os
import shutil
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
    assert out_empty == "[exit 0: no output] Command succeeded."
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


def test_tool_path_dirs_under_home_are_rebound_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    ws = home / "proj"
    dirs = {n: home / n for n in (".local/bin", ".ssh/bin", ".config/x", "proj/node_modules/.bin")}
    for d in dirs.values():
        d.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [
                str(dirs[".local/bin"]),
                str(dirs[".ssh/bin"]),  # credentials dir: never re-exposed
                str(dirs[".config/x"]),
                str(dirs["proj/node_modules/.bin"]),  # inside the workspace already
                str(home),  # a hidden root itself
                str(tmp_path / "missing"),
                "relative/bin",
                "/usr/bin",  # not masked: already visible
                str(dirs[".local/bin"]),  # duplicate
            ]
        ),
    )
    args = SandboxPolicy(workspace_root=ws)._tool_path_mounts([])
    good = str(dirs[".local/bin"].resolve())
    assert args == ["--ro-bind", good, good]


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bwrap")
async def test_tool_on_path_under_home_runs_inside_the_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True)
    tool = bindir / "mytool"
    tool.write_text("#!/bin/sh\necho tool-ok\n")
    tool.chmod(0o755)
    ws = home / "proj"
    ws.mkdir()
    (home / "secret.txt").write_text("nope")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    sp = SandboxPolicy(workspace_root=ws)
    code, out = await sp.execute_bash_with_code("mytool; ls ~/..; echo end")
    assert "tool-ok" in out and "secret.txt" not in out, out


def _venv_with_home_interpreter(home: Path, ws: Path) -> Path:
    root = home / ".local" / "share" / "uv" / "python"
    (root / "cpython-3.14.4").mkdir(parents=True)
    prefix = root / "cpython-3.14"
    prefix.symlink_to(root / "cpython-3.14.4")
    (prefix / "bin").mkdir()
    interp = prefix / "bin" / "mytool"
    interp.write_text("#!/bin/sh\necho venv-ok\n")
    interp.chmod(0o755)
    (ws / ".venv" / "bin").mkdir(parents=True)
    (ws / ".venv" / "bin" / "mytool").symlink_to(interp)
    (ws / ".venv" / "pyvenv.cfg").write_text(f"home = {prefix / 'bin'}\nuv = 0.1\n")
    return prefix


def test_venv_interpreter_prefix_is_re_exposed_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #76: a workspace .venv whose python lives under ~/.local/share/uv must still start
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin")
    ws = home / "proj"
    ws.mkdir(parents=True)
    prefix = _venv_with_home_interpreter(home, ws)
    sp = SandboxPolicy(workspace_root=ws)
    assert sp._venv_prefixes() == [str(prefix)]
    real = str(prefix.resolve())
    assert sp._tool_path_mounts([str(home)]) == [
        *("--ro-bind", real, real),
        *("--symlink", real, str(prefix)),
    ]
    (ws / ".venv" / "pyvenv.cfg").write_text("home = /nowhere\n")  # no bin/ suffix kept as is
    assert sp._venv_prefixes() == ["/nowhere"]
    (ws / ".venv" / "pyvenv.cfg").write_text("nothing here\n")
    assert sp._venv_prefixes() == []


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bwrap")
async def test_workspace_venv_runs_inside_the_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    ws = home / "proj"
    ws.mkdir(parents=True)
    _venv_with_home_interpreter(home, ws)
    (home / "secret.txt").write_text("nope")
    monkeypatch.setenv("HOME", str(home))
    sp = SandboxPolicy(workspace_root=ws)
    code, out = await sp.execute_bash_with_code(".venv/bin/mytool; ls ~/..; echo end")
    assert "venv-ok" in out and "secret.txt" not in out, out


async def test_bash_output_drops_workspace_prefix_and_rule_lines(tmp_path: Path) -> None:
    """North star: drop the absolute workspace path and ==== / ---- rule lines (tokens)."""
    sandbox = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    cmd = f"printf '{tmp_path}/a.py:3 boom\\n{'=' * 70}\\nFAIL x\\n{'-' * 70}\\nkeep\\n'"
    out = await sandbox.execute_bash(cmd)
    assert str(tmp_path) not in out
    assert out == "a.py:3 boom\nFAIL x\nkeep\n"


def test_compact_output_collapses_long_tracebacks_to_last_two_frames() -> None:
    """North star: tracebacks are ~half of observation chars; keep the call site and the cause."""
    from tether.sandbox import _compact_output

    def frame(n: int) -> str:
        return f'  File "m.py", line {n}, in f{n}\n    call_{n}()\n           ^^^^^^\n'

    tb = "Traceback (most recent call last):\n" + "".join(frame(n) for n in range(1, 6))
    out = _compact_output(tb + "ValueError: boom\nok line\n", Path("/ws"))
    assert out == (
        "Traceback (most recent call last):\n  ... 3 frames ...\n"
        '  File "m.py", line 4, in f4\n    call_4()\n'
        '  File "m.py", line 5, in f5\n    call_5()\n'
        "ValueError: boom\nok line\n"
    )
    short = "Traceback (most recent call last):\n" + frame(1) + "KeyError: 1\n"
    assert _compact_output(short, Path("/ws")).count("File") == 1
    assert "^^^" not in _compact_output(short, Path("/ws"))
