"""Tests for optional resource limits on sandboxed bash commands (#124 item 6).

Real-subprocess tests are Linux-only and bypass bwrap, so the host layout does not matter.
"""

from __future__ import annotations

import asyncio
import os
import resource
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy

LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="rlimits are enforced on Linux")
NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores RLIMIT_NPROC"
)
NEEDS_BWRAP = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not installed")
MIB = 1024 * 1024


def _policy(tmp_path: Path, **kwargs: Any) -> SandboxPolicy:
    """Host-agnostic policy: no bwrap, explicit unsandboxed opt-in, workspace in tmp_path."""
    return SandboxPolicy(
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
        allow_unsandboxed=True,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ({"cpus": 1}, "cpus"),
        ({"cpu": 0}, "cpu"),
        ({"mem": -1}, "mem"),
        ({"cpu": True}, "cpu"),
        ({"cpu": "x"}, "cpu"),
        (["cpu"], "cpu"),
        (["cpu=1", "cpu=2"], "cpu"),
    ],
)
def test_limits_validation(tmp_path: Path, raw: Any, key: str) -> None:
    with pytest.raises(ValueError, match=key):
        SandboxPolicy(workspace_root=tmp_path, limits=raw)


@LINUX_ONLY
def test_limits_accepts_known_keys(tmp_path: Path) -> None:
    policy = SandboxPolicy(
        workspace_root=tmp_path, limits={"cpu": 1, "mem": 64, "procs": 8, "fsize": 10}
    )
    assert policy.limits == {"cpu": 1, "mem": 64, "procs": 8, "fsize": 10}


@LINUX_ONLY
async def test_cpu_limit_hit(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"cpu": 1}, timeout_seconds=20)
    started = time.monotonic()
    rc, out = await policy.execute_bash_with_code("while :; do :; done")
    elapsed = time.monotonic() - started
    assert rc != 0
    assert elapsed < 10, "stopped by the wall-clock timeout, not by RLIMIT_CPU"
    assert out.strip().splitlines()[-1].startswith("[limit hit: cpu 1s] Instead:"), out


@LINUX_ONLY
@NEEDS_BWRAP
async def test_cpu_limit_hit_in_bwrap(tmp_path: Path) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, limits={"cpu": 1}, timeout_seconds=20)
    rc, out = await policy.execute_bash_with_code("while :; do :; done")
    assert rc != 0
    assert out.strip().splitlines()[-1].startswith("[limit hit: cpu 1s] Instead:"), out


@LINUX_ONLY
async def test_fsize_limit_hit(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"fsize": 1}, timeout_seconds=20)
    rc, out = await policy.execute_bash_with_code("head -c 3000000 /dev/zero > big.bin")
    assert rc != 0
    assert "[limit hit: fsize 1 MB]" in out, out
    assert (tmp_path / "big.bin").stat().st_size <= MIB


@LINUX_ONLY
async def test_fsize_limit_hit_python_write(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"fsize": 1}, timeout_seconds=20)
    cmd = 'python3 -c \'open("big.bin", "w").write("x" * 3000000)\''
    rc, out = await policy.execute_bash_with_code(cmd)
    assert rc != 0
    assert "[limit hit: fsize 1 MB]" in out, out


@LINUX_ONLY
@NOT_ROOT
async def test_procs_limit_enforced(tmp_path: Path) -> None:
    procs_policy = _policy(tmp_path, limits={"procs": 1}, timeout_seconds=20)
    _, out = await procs_policy.execute_bash_with_code("python3 -c 'import os; os.fork()'")
    assert "[limit hit: procs 1]" in out, out


@LINUX_ONLY
@NOT_ROOT
async def test_mem_limit_enforced(tmp_path: Path) -> None:
    mem_policy = _policy(tmp_path, limits={"mem": 64}, timeout_seconds=20)
    cmd = "python3 -c 'b = bytearray(512 * 2**20)'"
    rc, out = await mem_policy.execute_bash_with_code(cmd)
    assert rc != 0
    assert "[limit hit: mem 64 MB]" in out, out


def test_limits_refused_off_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(ValueError, match="mem"):
        SandboxPolicy(workspace_root=tmp_path, limits={"mem": 1})


@LINUX_ONLY
def test_limit_hit_procs_and_mem_branches(tmp_path: Path) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, limits={"procs": 2, "mem": 64})
    procs = policy._limit_hit(1, "BlockingIOError: [Errno 11] Resource temporarily unavailable")
    assert procs is not None and procs.startswith("[limit hit: procs 2] Instead:")
    assert (policy._limit_hit(254, "bash: fork: retry: x") or "").startswith("[limit hit: procs")
    mem = policy._limit_hit(1, "MemoryError")
    assert mem is not None and mem.startswith("[limit hit: mem 64 MB] Instead:")
    assert policy._limit_hit(0, "MemoryError") is None
    assert policy._limit_hit(1, "plain error") is None


@LINUX_ONLY
def test_limit_hit_sigkill_needs_cpu_time(tmp_path: Path) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, limits={"cpu": 30})
    assert policy._limit_hit(-9, "", cpu_used=0.01) is None
    assert policy._limit_hit(137, "") is None
    assert (policy._limit_hit(-9, "", cpu_used=30.0) or "").startswith("[limit hit: cpu 30s]")
    assert (policy._limit_hit(-24, "") or "").startswith("[limit hit: cpu 30s]")


@LINUX_ONLY
async def test_kill_9_is_not_a_cpu_hit(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"cpu": 30}, timeout_seconds=20)
    rc, out = await policy.execute_bash_with_code("kill -9 $$")
    assert rc in (-9, 137)
    assert "[limit hit" not in out, out


async def test_no_limits_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeProc:
        pid = 1
        returncode = 0

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            return b"hi\n", b""

    async def fake_exec(*argv: str, **kwargs: Any) -> FakeProc:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    policy = _policy(tmp_path)
    rc, out = await policy.execute_bash_with_code("echo hi")

    assert captured["argv"] == policy._build_exec_argv("echo hi")
    assert "preexec_fn" not in captured["kwargs"]
    assert captured["kwargs"]["env"] == policy.scrub_env()
    assert "limits" not in policy.to_dict()
    assert rc == 0
    assert out.strip() == "hi"


@LINUX_ONLY
def test_children_only_lower(tmp_path: Path) -> None:
    parent = SandboxPolicy(workspace_root=tmp_path, limits={"cpu": 10})
    assert parent.attenuate(child_limits={"cpu": 5}).limits == {"cpu": 5}
    assert parent.attenuate(child_limits={"mem": 100}).limits == {"cpu": 10, "mem": 100}
    with pytest.raises(ValueError, match="cpu"):
        parent.attenuate(child_limits={"cpu": 20})
    assert parent.attenuate().limits == {"cpu": 10}
    assert SandboxPolicy.from_dict(parent.to_dict()).limits == {"cpu": 10}


@LINUX_ONLY
def test_limit_setter_calls_setrlimit(monkeypatch: pytest.MonkeyPatch) -> None:
    inf = resource.RLIM_INFINITY
    current = {resource.RLIMIT_NPROC: (inf, 4)}
    calls: dict[int, tuple[int, int]] = {}

    def fake_get(res: int) -> tuple[int, int]:
        return current.get(res, (inf, inf))

    def fake_set(res: int, pair: tuple[int, int]) -> None:
        calls[res] = pair

    monkeypatch.setattr(resource, "getrlimit", fake_get)
    monkeypatch.setattr(resource, "setrlimit", fake_set)
    sb_mod._limit_setter({"cpu": 3, "mem": 64, "procs": 8, "fsize": 2})()

    assert calls == {
        resource.RLIMIT_CPU: (3, 4),
        resource.RLIMIT_DATA: (64 * MIB, 64 * MIB),
        resource.RLIMIT_NPROC: (4, 4),
        resource.RLIMIT_FSIZE: (2 * MIB, 2 * MIB),
    }


@LINUX_ONLY
def test_limit_hit_none_for_plain_failure(tmp_path: Path) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, limits={"cpu": 1, "fsize": 1})
    assert policy._limit_hit(1, "some plain error") is None


@LINUX_ONLY
async def test_successful_command_output_unchanged(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"cpu": 5, "fsize": 1})
    rc, out = await policy.execute_bash_with_code("echo ok")
    assert rc == 0
    assert out.strip() == "ok"


@LINUX_ONLY
async def test_hit_line_is_last_after_truncation(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"cpu": 1}, max_output_chars=200, timeout_seconds=20)
    cmd = "yes abcdefgh | head -c 5000; while :; do :; done"
    _, out = await policy.execute_bash_with_code(cmd)
    assert "[truncated" in out, out
    assert out.strip().splitlines()[-1].startswith("[limit hit: cpu 1s] Instead:"), out


@LINUX_ONLY
async def test_wall_clock_timeout_has_no_hit_line(tmp_path: Path) -> None:
    policy = _policy(tmp_path, limits={"cpu": 20}, timeout_seconds=1)
    rc, out = await policy.execute_bash_with_code("sleep 5")
    assert rc == 124
    assert "timed out" in out
    assert "[limit hit" not in out


class _StopHere(Exception):
    pass


def _stub_harness(seen: dict[str, Any]) -> Any:
    def stub(*args: Any, **kwargs: Any) -> None:
        seen["sandbox"] = kwargs["sandbox"]
        raise _StopHere

    return stub


def test_cli_limit_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tether import cli

    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "Harness", _stub_harness(seen))
    assert cli.main(["run", "--limit", "bogus=1", "task"]) == 1
    assert "Error: --limit" in capsys.readouterr().err
    assert "sandbox" not in seen

    monkeypatch.setattr(sys, "platform", "linux")
    for sub in (["run"], ["pipeline", "p.yaml"]):
        seen.clear()
        with pytest.raises(_StopHere):
            cli.main([*sub, "--limit", "cpu=60", "--limit", "mem=2048", "task"])
        assert seen["sandbox"].limits == {"cpu": 60, "mem": 2048}


def test_cli_limit_refused_off_linux(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tether import cli

    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "Harness", _stub_harness(seen))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert cli.main(["run", "--limit", "mem=1", "task"]) == 1
    assert "Error: --limit: limit mem: needs Linux" in capsys.readouterr().err
    assert "sandbox" not in seen
