"""Landlock: an unprivileged filesystem jail for Linux, the fallback when bwrap is blocked (AD-35).

Kernel docs: https://docs.kernel.org/userspace-api/landlock.html. Stdlib and ctypes only.
`python -m tether.landlock [--ro P]... [--rw P]... [--dev] -- prog args...` restricts this
process, then execs `prog`. Any failure prints one line and exits 126: it never execs
unconfined. Landlock restricts file access only; it cannot block network or unix-socket
connects (AD-35 ceilings).
"""

from __future__ import annotations

import ctypes
import errno
import functools
import os
import platform
import stat
import struct
import sys
from collections.abc import Sequence

_NR_CREATE_RULESET = 444
_NR_ADD_RULE = 445
_NR_RESTRICT_SELF = 446
_CREATE_VERSION_FLAG = 1
_RULE_PATH_BENEATH = 1
_PR_SET_NO_NEW_PRIVS = 38
_ARCHES = ("x86_64", "aarch64")

EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
MAKE_SYM = 1 << 12
REFER = 1 << 13  # ABI >= 2
TRUNCATE = 1 << 14  # ABI >= 3
IOCTL_DEV = 1 << 15  # ABI >= 5

_FILE_RIGHTS = EXECUTE | WRITE_FILE | READ_FILE | TRUNCATE
_RO = READ_FILE | READ_DIR | EXECUTE


class LandlockError(Exception):
    """A step failed; the message names the step and the errno text."""


class _RulesetAttr(ctypes.Structure):
    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    ]


@functools.cache
def _libc() -> ctypes.CDLL:
    lib = ctypes.CDLL(None, use_errno=True)
    lib.syscall.restype = ctypes.c_long
    return lib


def _syscall(nr: int, *args: object) -> int:
    # Every integer goes out as a C long: the syscall reads them as 64-bit values.
    cargs = [ctypes.c_long(a) if isinstance(a, int) else a for a in args]
    return int(_libc().syscall(ctypes.c_long(nr), *cargs))


def abi() -> int:
    """The Landlock ABI version of this kernel, or 0 when it is missing or unusable here."""
    if sys.platform != "linux" or platform.machine() not in _ARCHES:
        return 0
    got = _syscall(_NR_CREATE_RULESET, None, 0, _CREATE_VERSION_FLAG)
    return got if got > 0 else 0


def _handled(version: int) -> int:
    """Every filesystem right the running ABI knows; a right the kernel lacks is EINVAL."""
    mask = (MAKE_SYM << 1) - 1
    if version >= 2:
        mask |= REFER
    if version >= 3:
        mask |= TRUNCATE
    if version >= 5:
        mask |= IOCTL_DEV
    return mask


def _fail(step: str, err: int) -> LandlockError:
    return LandlockError(f"{step}: {os.strerror(err)}")


def _add(ruleset: int, path: str, rights: int, handled: int) -> None:
    fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    try:
        mask = rights & handled
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            mask &= _FILE_RIGHTS  # a directory-only right on a file is EINVAL
        # struct landlock_path_beneath_attr is packed: u64 allowed_access, s32 parent_fd (12 B)
        rule = ctypes.create_string_buffer(struct.pack("=Qi", mask, fd), 12)
        if _syscall(_NR_ADD_RULE, ruleset, _RULE_PATH_BENEATH, ctypes.byref(rule), 0) != 0:
            raise _fail(f"landlock_add_rule {path}", ctypes.get_errno())
    finally:
        os.close(fd)


def restrict(ro: Sequence[str], rw: Sequence[str], dev: bool) -> None:
    """Confine this process: `ro` read-only, `rw` read-write, `/dev` usable when `dev`."""
    version = abi()
    if version == 0:
        raise LandlockError(f"landlock unavailable: {os.strerror(errno.ENOSYS)}")
    if _libc().prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise _fail("prctl(PR_SET_NO_NEW_PRIVS)", ctypes.get_errno())
    handled = _handled(version)
    size = 8 if version < 4 else 16 if version < 6 else 24  # the struct grew per ABI
    attr = _RulesetAttr(handled, 0, 0)  # net and scoped stay unrestricted
    ruleset = _syscall(_NR_CREATE_RULESET, ctypes.byref(attr), size, 0)
    if ruleset < 0:
        raise _fail("landlock_create_ruleset", ctypes.get_errno())
    try:
        for path in ro:
            if os.path.exists(path):
                _add(ruleset, path, _RO, handled)
        for path in rw:
            if os.path.exists(path):
                _add(ruleset, path, handled, handled)
        if dev:
            dev_rights = READ_FILE | WRITE_FILE | (IOCTL_DEV if handled & IOCTL_DEV else 0)
            _add(ruleset, "/dev", dev_rights, handled)
        if _syscall(_NR_RESTRICT_SELF, ruleset, 0) != 0:
            raise _fail("landlock_restrict_self", ctypes.get_errno())
    finally:
        os.close(ruleset)


_USAGE = "usage: python -m tether.landlock [--ro P]... [--rw P]... [--dev] -- prog args..."


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    if "--" not in args or not args[args.index("--") + 1 :]:
        print(_USAGE, file=sys.stderr)
        return 2
    split = args.index("--")
    ro: list[str] = []
    rw: list[str] = []
    dev = False
    opts = iter(args[:split])
    for opt in opts:
        if opt == "--dev":
            dev = True
        elif opt in ("--ro", "--rw"):
            path = next(opts, None)
            if path is None:
                print(_USAGE, file=sys.stderr)
                return 2
            (ro if opt == "--ro" else rw).append(path)
        else:
            print(_USAGE, file=sys.stderr)
            return 2
    prog = args[split + 1 :]
    try:
        restrict(ro, rw, dev)
    except (LandlockError, OSError) as exc:
        print(f"tether.landlock: {exc}", file=sys.stderr)
        return 126
    try:
        os.execvp(prog[0], prog)
    except OSError as exc:
        print(f"tether.landlock: exec {prog[0]}: {exc.strerror}", file=sys.stderr)
        return 127
    return 0  # reached only when execvp is replaced by a test double


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
