"""Unit tests for _host_socket_masks() bwrap argument generation."""

from __future__ import annotations

import pytest

import tether.sandbox as sb_mod


def test_host_socket_masks_empty_without_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_mod, "_host_socket_paths", lambda: ())
    assert sb_mod._host_socket_masks() == ()


def test_host_socket_masks_binds_empty_file_over_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_mod, "_host_socket_paths", lambda: ("/run/x.sock",))
    empty = sb_mod._empty_mask_file()
    assert sb_mod._host_socket_masks() == ("--ro-bind", empty, "/run/x.sock")
