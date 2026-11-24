"""Landlock fallback (AD-35): the module on the real kernel, and the sandbox that uses it.

Cases that restrict a process run in a child interpreter, so pytest is never confined.
"""

from __future__ import annotations

import ctypes
import errno
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import tether.sandbox as sb_mod
from tether import doctor, landlock
from tether.sandbox import BwrapProbe, SandboxPolicy, SandboxViolationError

needs_landlock = pytest.mark.skipif(landlock.abi() == 0, reason="kernel has no Landlock")

_MAIN = (
    "import sys, errno, ctypes\nimport tether.landlock as l\n{setup}"
    "raise SystemExit(l.main(sys.argv[1:]))\n"
)
# Each step's failure, injected in the child: the program must not run and exit must be 126.


def _fail_syscall(nr: int, flags_zero: bool = False) -> str:
    """Setup code: make syscall `nr` (only with flags 0 when asked) fail with EINVAL."""
    cond = f"nr == {nr}" + (" and a[2] == 0" if flags_zero else "")
    return (
        "_orig = l._syscall\n"
        "def _bad(nr, *a):\n"
        "    if " + cond + ":\n"
        "        ctypes.set_errno(errno.EINVAL)\n"
        "        return -1\n"
        "    return _orig(nr, *a)\n"
        "l._syscall = _bad\n"
    )


_PRCTL_FAILS = (
    "class _L:\n"
    "    syscall = ctypes.CDLL(None, use_errno=True).syscall\n"
    "    prctl = staticmethod(lambda *a: -1)\n"
    "l._libc = lambda: _L\n"
)
_FAILS = {
    "prctl": _PRCTL_FAILS,
    "create": _fail_syscall(444, flags_zero=True),
    "add": _fail_syscall(445),
    "self": _fail_syscall(446),
    "open": "def _denied(*a, **k):\n    raise OSError(13, 'Denied')\nl.os.open = _denied\n",
    "exec": "l.restrict = lambda *a: None\n",
    "unavailable": "l.abi = lambda: 0\n",
}


def _child(setup: str, *args: str) -> subprocess.CompletedProcess[str]:
    code = _MAIN.format(setup=_FAILS.get(setup, ""))
    return subprocess.run(
        [sys.executable, "-P", "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _jail(ws: Path, script: str) -> subprocess.CompletedProcess[str]:
    """Run `script` under the module's own jail: the host readable, `ws` writable."""
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            landlock.__file__,
            "--ro",
            "/",
            "--rw",
            str(ws),
            "--dev",
            "--",
            "bash",
            "-c",
            script,
        ],
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@needs_landlock
def test_abi_reports_this_kernel() -> None:
    assert landlock.abi() >= 1


def test_abi_is_zero_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert landlock.abi() == 0


def test_handled_rights_grow_with_the_abi() -> None:
    assert landlock._handled(1) == 0x1FFF
    assert not landlock._handled(1) & landlock.REFER
    assert landlock._handled(2) & landlock.REFER
    assert landlock._handled(3) & landlock.TRUNCATE
    assert landlock._handled(5) & landlock.IOCTL_DEV


@needs_landlock
def test_jail_allows_the_workspace_and_dev_null_and_nothing_else(tmp_path: Path) -> None:
    ws, other = tmp_path / "ws", tmp_path / "other"
    ws.mkdir()
    other.mkdir()
    done = _jail(ws, "echo x > ok.txt && echo fine; echo y > /dev/null && echo devok")
    assert done.returncode == 0, done.stderr
    assert "fine" in done.stdout and "devok" in done.stdout
    assert (ws / "ok.txt").read_text() == "x\n"
    denied = _jail(ws, f"echo z > {other}/no.txt")
    assert denied.returncode != 0 and "Permission denied" in denied.stderr
    assert not (other / "no.txt").exists()


@needs_landlock
def test_jailed_program_runs_with_no_new_privileges(tmp_path: Path) -> None:
    done = _jail(tmp_path, "grep NoNewPrivs /proc/self/status")
    assert done.returncode == 0 and done.stdout.split()[-1] == "1"


@pytest.mark.parametrize(
    ("setup", "step"),
    [
        ("unavailable", "landlock unavailable"),
        ("prctl", "prctl(PR_SET_NO_NEW_PRIVS)"),
        ("create", "landlock_create_ruleset"),
        ("add", "landlock_add_rule"),
        ("self", "landlock_restrict_self"),
        ("open", "Denied"),
    ],
)
def test_a_failing_step_exits_126_and_the_program_never_runs(
    tmp_path: Path, setup: str, step: str
) -> None:
    marker = tmp_path / "ran"
    done = _child(setup, "--rw", str(tmp_path), "--", "touch", str(marker))
    assert done.returncode == 126, done.stderr
    assert step in done.stderr
    assert not marker.exists()


def test_exec_failure_exits_127(tmp_path: Path) -> None:
    done = _child("exec", "--", str(tmp_path / "no-such-program"))
    assert done.returncode == 127 and "exec" in done.stderr


def test_usage_errors_exit_2_before_any_kernel_call(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in ([], ["--"], ["--ro", "/"], ["--ro", "--", "true"], ["--bogus", "--", "true"]):
        assert landlock.main(argv) == 2
    assert "usage: python -m tether.landlock" in capsys.readouterr().err


def test_host_read_roots_skip_hidden_dirs_and_links_into_them() -> None:
    got = sb_mod._host_read_roots({"/usr", "/run", "/home"})
    assert "/usr" not in got and "/home" not in got
    assert "/var/run" not in got  # a link into /run
    assert "/etc" in got


def test_landlock_is_the_jail_when_bwrap_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    monkeypatch.setattr(landlock, "abi", lambda: 8)
    assert sb_mod._jail() == "landlock"
    assert SandboxPolicy().mode() == "landlock"
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: True)
    assert sb_mod._jail() == "bwrap" and SandboxPolicy().mode() == "bwrap"
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    monkeypatch.setattr(landlock, "abi", lambda: 0)
    assert sb_mod._jail() is None
    assert SandboxPolicy().mode() == "command checks only"
    assert SandboxPolicy(use_kernel_sandbox=False).mode() == "command checks only"


def test_no_jail_refusal_names_both(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    monkeypatch.setattr(landlock, "abi", lambda: 0)
    msg = SandboxPolicy(workspace_root=tmp_path).isolation_error()
    assert msg is not None
    assert "Install bubblewrap" in msg and "--allow-unsandboxed" in msg
    assert "Landlock" in msg


def test_doctor_passes_on_landlock_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: 8)
    monkeypatch.setattr(
        doctor, "bwrap_probe", lambda: BwrapProbe("blocked", "/usr/bin/bwrap", "EPERM")
    )
    by = {c.name: c for c in doctor.run_checks("openai/x", "http://h:1", tmp_path / "t.db")}
    assert by["bwrap"].ok
    assert "bwrap blocked: EPERM" in by["bwrap"].detail and "Landlock ABI 8" in by["bwrap"].detail
    monkeypatch.setattr(doctor, "bwrap_probe", lambda: BwrapProbe("missing", "", ""))
    by = {c.name: c for c in doctor.run_checks("openai/x", "http://h:1", tmp_path / "t.db")}
    assert by["bwrap"].ok and "bwrap not installed" in by["bwrap"].detail


@needs_landlock
async def test_write_sessions_run_jailed_without_bwrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    ws, other = tmp_path / "ws", tmp_path / "other"
    ws.mkdir()
    other.mkdir()
    policy = SandboxPolicy(workspace_root=ws)
    assert policy.isolation_error() is None
    assert policy.mode() == "landlock"
    assert (await policy.execute_bash("echo hi > ok.txt && cat ok.txt")).strip() == "hi"
    assert Path((await policy.execute_bash("echo $TMPDIR")).strip()).name.startswith("tether-tmp-")
    text = await policy.execute_bash(f"python3 -c \"open('{other}/no.txt','w')\"; echo rc=$?")
    assert "Permission denied" in text and "rc=1" in text
    assert not (other / "no.txt").exists()
    with pytest.raises(SandboxViolationError, match="protected path"):
        await policy.execute_bash("cat .env")
    with pytest.raises(SandboxViolationError, match="network isolation"):
        await SandboxPolicy(workspace_root=ws, network=False).execute_bash("echo hi")


@needs_landlock
async def test_host_tmp_is_hidden_dns_config_stays_readable_and_signals_stay_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    ws = tmp_path / "ws"
    ws.mkdir()
    policy = SandboxPolicy(workspace_root=ws)
    # bwrap gives an empty /tmp; here the host /tmp (other sessions' files) must not be listable
    assert "rc=2" in await policy.execute_bash("ls /tmp >/dev/null; echo rc=$?")
    # DNS: /etc/resolv.conf links into /run/systemd/resolve on systemd hosts
    # (built at runtime: the fallback text rules refuse an absolute path typed in the command)
    text = await policy.execute_bash(
        "python3 -c \"open('/' + 'etc/resolv.conf').read()\"; echo rc=$?"
    )
    assert "rc=0" in text
    if landlock.abi() >= 6:  # scoped signals: the harness outside the jail cannot be signalled
        text = await policy.execute_bash(
            f'python3 -c "import os; os.kill({os.getpid()}, 0)"; echo rc=$?'
        )
        assert "PermissionError" in text and "rc=1" in text


@needs_landlock
async def test_hidden_home_is_unreadable_from_the_jail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    fake_home = tmp_path / "home" / "u"
    fake_home.mkdir(parents=True)
    secret = fake_home / "secret.txt"
    secret.write_text("s3cret")
    monkeypatch.setenv("HOME", str(fake_home))  # its top (`/tmp`) is hidden from the jail
    ws = tmp_path / "ws"
    ws.mkdir()
    text = await SandboxPolicy(workspace_root=ws).execute_bash(
        f"python3 -c \"print(open('{secret}').read())\"; echo rc=$?"
    )
    assert "s3cret" not in text and "rc=1" in text


@needs_landlock
async def test_read_only_profile_cannot_write_in_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    (tmp_path / "in.txt").write_text("v")
    ro = SandboxPolicy(profile="read-only", workspace_root=tmp_path)
    assert (await ro.execute_bash("cat in.txt")).strip() == "v"
    # The text rules refuse `>` in this profile, so reach the kernel layer directly.
    argv = ro._build_exec_argv("echo x > w.txt; echo rc=$?")
    _, text = await ro._run_argv(argv, None, env=ro.scrub_env(), cwd=str(tmp_path))
    assert "Permission denied" in text and "rc=1" in text
    assert not (tmp_path / "w.txt").exists()


# In-process cases: the syscalls are faked, so pytest is never restricted. The real kernel
# is covered above by the child-process cases (coverage does not follow child processes).


_REAL_OPEN = os.open


def _fake_kernel(
    monkeypatch: pytest.MonkeyPatch,
    fail: str | None = None,
    rules: list[tuple[int, bytes]] | None = None,
) -> None:
    """Fake the three Landlock syscalls and prctl. `fail` names the step that errors."""

    def fake_syscall(nr: int, *args: object) -> int:
        if nr == 444 and args[2] == 1:  # abi() probe
            return 8
        if nr == 444:
            if fail == "create":
                ctypes.set_errno(errno.EINVAL)
                return -1
            return _REAL_OPEN(os.devnull, os.O_RDONLY)  # restrict() closes it: a real fd
        if nr == 445:
            if rules is not None:
                rules.append((int(args[1]), args[2]._obj.raw))  # type: ignore[attr-defined]
            if fail == "add":
                ctypes.set_errno(errno.EINVAL)
                return -1
            return 0
        if fail == "self":
            ctypes.set_errno(errno.EPERM)
            return -1
        return 0

    class FakeLib:
        @staticmethod
        def prctl(*args: int) -> int:
            if fail == "prctl":
                ctypes.set_errno(errno.EPERM)
                return -1
            return 0

    monkeypatch.setattr(landlock, "_syscall", fake_syscall)
    monkeypatch.setattr(landlock, "_libc", lambda: FakeLib)


def test_restrict_adds_one_rule_per_path_with_file_rights_on_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules: list[tuple[int, bytes]] = []
    _fake_kernel(monkeypatch, rules=rules)
    f = tmp_path / "f.txt"
    f.write_text("x")
    landlock.restrict([str(tmp_path), str(f), "/no/such/path"], [str(tmp_path)], dev=True)
    assert len(rules) == 4  # ro dir, ro file, rw dir, /dev (missing ro path is skipped)
    masks = [struct.unpack("=Qi", raw[:12])[0] for _, raw in rules]
    assert masks[1] == landlock.READ_FILE | landlock.EXECUTE  # a file takes file rights only
    assert masks[0] == landlock._RO
    assert masks[2] & landlock.MAKE_DIR  # rw dir: every handled right
    assert masks[3] & landlock.IOCTL_DEV  # /dev on ABI >= 5


@pytest.mark.parametrize(
    ("fail", "step"),
    [
        ("prctl", "prctl(PR_SET_NO_NEW_PRIVS)"),
        ("create", "landlock_create_ruleset"),
        ("add", "landlock_add_rule"),
        ("self", "landlock_restrict_self"),
    ],
)
def test_restrict_names_the_step_that_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: str, step: str
) -> None:
    _fake_kernel(monkeypatch, fail=fail)
    with pytest.raises(landlock.LandlockError, match=re.escape(step)):
        landlock.restrict([str(tmp_path)], [str(tmp_path)], dev=False)


def test_restrict_refuses_when_the_kernel_has_no_landlock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(landlock, "abi", lambda: 0)
    with pytest.raises(landlock.LandlockError, match="unavailable"):
        landlock.restrict([], [], dev=False)


def test_main_exits_126_on_open_failure_and_127_on_exec_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_kernel(monkeypatch)

    def denied(*a: object, **k: object) -> int:
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(landlock.os, "open", denied)
    assert landlock.main(["--rw", str(tmp_path), "--", "true"]) == 126
    assert "Permission denied" in capsys.readouterr().err

    monkeypatch.setattr(landlock.os, "execvp", lambda *a: (_ for _ in ()).throw(OSError(2, "nope")))
    assert landlock.main(["--", "true"]) == 127


def test_main_execs_the_program_after_restricting(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_kernel(monkeypatch)
    ran: list[list[str]] = []
    monkeypatch.setattr(landlock.os, "execvp", lambda prog, argv: ran.append(argv))
    assert landlock.main(["--dev", "--", "true", "-x"]) == 0
    assert ran == [["true", "-x"]]
