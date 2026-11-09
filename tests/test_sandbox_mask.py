"""S8 (#124 item 1): kernel masks read as an EMPTY regular file, not a nodev `/dev/null`.

The real-bwrap tests build the git repo on the host first, so `git log` must exit 0 and no
`git -c` option ever goes through `validate_bash_command`.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy

SECRET = "TOKEN=hunter2"
GIT_CONFIG = "[core]\n\trepositoryformatversion = 0\n"
needs_bwrap = pytest.mark.skipif(not sb_mod._can_use_bwrap(), reason="needs a working bwrap")


def _helper() -> Callable[[], str]:
    helper = getattr(sb_mod, "_empty_mask_file", None)
    assert helper is not None, "tether.sandbox._empty_mask_file() is missing"
    return helper  # type: ignore[no-any-return]


@pytest.fixture
def fresh_mask(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[[], str]:
    """The helper with a reset cache and its private dirs created under tmp_path."""
    mask_tmp = tmp_path / "masktmp"
    mask_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(mask_tmp))
    monkeypatch.setattr(sb_mod, "_EMPTY_FILE", None, raising=False)
    return lambda: _helper()()  # resolved per call so a missing helper fails in the test body


def _assert_valid_empty(path: str) -> None:
    st = os.lstat(path)
    assert stat.S_ISREG(st.st_mode), f"{path} is not a regular file"
    assert st.st_size == 0
    assert st.st_mode & 0o777 == 0o444
    assert st.st_uid == os.getuid()


def _git(ws: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=ws,
        check=True,
        capture_output=True,
    )


def _masked_repo(ws: Path) -> Path:
    """A real git repo with one commit (`init`), a committed TODO note and a secret `.env`."""
    ws.mkdir()
    _git(ws, "init", "-q")
    (ws / "notes.txt").write_text("line one\nTODO: fix me\n")
    _git(ws, "add", "notes.txt")
    _git(ws, "commit", "-q", "-m", "init")
    (ws / ".env").write_text(SECRET)
    return ws


# --- DoD-1: real bwrap, masked files read as empty --------------------------------------------


@needs_bwrap
async def test_masked_env_reads_empty(tmp_path: Path) -> None:
    ws = _masked_repo(tmp_path / "ws")
    code, out = await SandboxPolicy(workspace_root=ws).execute_bash_with_code(
        "cat .env; echo rc=$?"
    )
    assert code == 0, out
    assert "hunter2" not in out, out
    assert out.strip() == "rc=0", out  # empty read, no "Permission denied"


@needs_bwrap
async def test_git_works_in_masked_repo(tmp_path: Path) -> None:
    ws = _masked_repo(tmp_path / "ws")
    sp = SandboxPolicy(workspace_root=ws)
    code, out = await sp.execute_bash_with_code("git status --short")
    assert code == 0, out
    assert "unable to access" not in out and "Permission denied" not in out, out
    code, out = await sp.execute_bash_with_code("git log --oneline")
    assert code == 0, out
    assert "init" in out and "unable to access" not in out, out


@needs_bwrap
async def test_recursive_grep_finds_match(tmp_path: Path) -> None:
    ws = _masked_repo(tmp_path / "ws")
    code, out = await SandboxPolicy(workspace_root=ws).execute_bash_with_code("grep -rn TODO .")
    assert code == 0, out
    assert "notes.txt" in out and "Permission denied" not in out, out
    assert "hunter2" not in out, out


# --- DoD-2: the mask stays a read-only mask -----------------------------------------------------


@needs_bwrap
@pytest.mark.parametrize("target", [".env", ".git/config"])
async def test_mask_is_read_only(tmp_path: Path, target: str) -> None:
    ws = _masked_repo(tmp_path / "ws")
    host = ws / target
    before = host.read_bytes()
    sp = SandboxPolicy(workspace_root=ws)
    # The mask is an empty regular file (not a char device) ...
    code, out = await sp.execute_bash_with_code(f"test -f {target} && test ! -s {target}")
    assert code == 0, f"{target} is not an empty regular file in the jail: {out}"
    # ... and every mutation fails, each checked on its own.
    for cmd in (
        f"echo x > {target}",
        f"echo x >> {target}",
        f": > {target}",
        f"truncate -s0 {target}",
        f"rm -f {target}",
    ):
        code, out = await sp.execute_bash_with_code(cmd)
        assert code != 0, f"`{cmd}` succeeded: {out}"
    assert host.read_bytes() == before


# --- DoD-3: args and helper ---------------------------------------------------------------------


def test_mask_args_use_empty_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = _helper()()
    (tmp_path / ".env").write_text(SECRET)
    (tmp_path / "k.pem").write_text("key")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(GIT_CONFIG)
    args = SandboxPolicy(workspace_root=tmp_path)._protected_mounts()
    assert "/dev/null" not in args, args
    for masked in (".env", "k.pem", ".git/config"):
        i = args.index(str(tmp_path / masked))
        assert args[i - 2 : i + 1] == ["--ro-bind", empty, str(tmp_path / masked)], args

    monkeypatch.setattr(sb_mod, "_host_socket_paths", lambda: ("/run/x.sock",), raising=False)
    assert sb_mod._host_socket_masks() == ("--ro-bind", empty, "/run/x.sock")


def test_nothing_to_mask_does_not_touch_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _helper()

    def boom() -> str:
        raise AssertionError("empty mask file requested with nothing to mask")

    monkeypatch.setattr(sb_mod, "_empty_mask_file", boom)
    (tmp_path / "a.txt").write_text("x")
    assert SandboxPolicy(workspace_root=tmp_path)._protected_mounts() == []


def test_empty_file_helper_idempotent(fresh_mask: Callable[[], str]) -> None:
    first = fresh_mask()
    assert fresh_mask() == first
    _assert_valid_empty(first)
    with ThreadPoolExecutor(max_workers=16) as pool:
        paths = set(pool.map(lambda _: fresh_mask(), range(64)))
    assert paths == {first}
    _assert_valid_empty(first)


def test_empty_file_concurrent_first_call(fresh_mask: Callable[[], str]) -> None:
    # Cold cache: racing first callers still share one file.
    with ThreadPoolExecutor(max_workers=16) as pool:
        paths = set(pool.map(lambda _: fresh_mask(), range(16)))
    assert len(paths) == 1
    _assert_valid_empty(paths.pop())


def test_empty_file_recreated_when_tampered(fresh_mask: Callable[[], str]) -> None:
    first = fresh_mask()
    os.unlink(first)
    second = fresh_mask()
    assert second != first
    _assert_valid_empty(second)

    os.chmod(second, 0o644)
    Path(second).write_text("x")
    third = fresh_mask()
    assert third != second  # a tampered file is never reused or repaired
    _assert_valid_empty(third)
    assert Path(second).read_text() == "x"


def test_empty_file_content_tampered_with_mode_restored(fresh_mask: Callable[[], str]) -> None:
    first = fresh_mask()
    os.chmod(first, 0o644)
    Path(first).write_text("x")
    os.chmod(first, 0o444)
    # Mode is back to 0o444 but content is not empty: the helper must still return an empty file.
    _assert_valid_empty(fresh_mask())


def test_empty_file_replaced_by_symlink_is_not_trusted(
    fresh_mask: Callable[[], str], tmp_path: Path
) -> None:
    first = fresh_mask()
    planted = tmp_path / "planted"
    planted.write_text("")
    planted.chmod(0o444)
    os.unlink(first)
    os.symlink(planted, first)
    second = fresh_mask()
    assert second != first
    _assert_valid_empty(second)


def test_empty_file_creation_failure_is_loud(
    fresh_mask: Callable[[], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_a: object, **_k: object) -> str:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(tempfile, "mkdtemp", fail)
    with pytest.raises(sb_mod.SandboxUnavailableError, match="TMPDIR"):
        fresh_mask()
