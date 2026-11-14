"""Unit tests for _host_socket_masks() bwrap argument generation."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

import tether.sandbox as sb_mod


@pytest.fixture
def socket_and_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path]]:
    """A real unix socket and an absolute symlink to it (AF_UNIX paths are short: bind relative)."""
    monkeypatch.chdir(tmp_path)
    sock = socket.socket(socket.AF_UNIX)
    sock.bind("real.sock")
    link = tmp_path / "link.sock"
    link.symlink_to(tmp_path / "real.sock")
    sb_mod._host_socket_paths.cache_clear()
    yield tmp_path / "real.sock", link
    sock.close()
    sb_mod._host_socket_paths.cache_clear()


def _glob_returning(
    monkeypatch: pytest.MonkeyPatch, first: list[str], second: list[str] | None = None
) -> None:
    results = {"/run/*": first, "/run/*/*": second or []}
    monkeypatch.setattr(sb_mod.glob, "glob", lambda pattern: list(results[pattern]))


def test_host_socket_paths_returns_real_path_once(
    monkeypatch: pytest.MonkeyPatch, socket_and_link: tuple[Path, Path]
) -> None:
    real, link = socket_and_link
    _glob_returning(monkeypatch, [str(real), str(link)])
    assert sb_mod._host_socket_paths() == (os.path.realpath(real),)


def test_host_socket_paths_masks_target_of_lone_symlink(
    monkeypatch: pytest.MonkeyPatch, socket_and_link: tuple[Path, Path]
) -> None:
    real, link = socket_and_link
    _glob_returning(monkeypatch, [], [str(link)])
    assert sb_mod._host_socket_paths() == (os.path.realpath(real),)


def test_host_socket_paths_skips_non_sockets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plain = tmp_path / "plain.txt"
    plain.write_text("x")
    _glob_returning(monkeypatch, [str(plain)])
    sb_mod._host_socket_paths.cache_clear()
    try:
        assert sb_mod._host_socket_paths() == ()
    finally:
        sb_mod._host_socket_paths.cache_clear()


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bwrap")
def test_bwrap_accepts_real_socket_mask_but_not_symlink(
    monkeypatch: pytest.MonkeyPatch, socket_and_link: tuple[Path, Path]
) -> None:
    real, link = socket_and_link
    _glob_returning(monkeypatch, [str(real), str(link)])
    masks = sb_mod._host_socket_masks()
    base = ["bwrap", "--ro-bind", "/", "/"]
    ok = subprocess.run([*base, *masks, "true"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    raw = ("--ro-bind", sb_mod._empty_mask_file(), str(link))
    bad = subprocess.run([*base, *raw, "true"], capture_output=True, text=True)
    assert bad.returncode != 0


def test_host_socket_masks_empty_without_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_mod, "_host_socket_paths", lambda: ())
    assert sb_mod._host_socket_masks() == ()


def test_host_socket_masks_binds_empty_file_over_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_mod, "_host_socket_paths", lambda: ("/run/x.sock",))
    empty = sb_mod._empty_mask_file()
    assert sb_mod._host_socket_masks() == ("--ro-bind", empty, "/run/x.sock")
