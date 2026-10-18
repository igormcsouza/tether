"""Regression tests from the v0.1.4 red-team run (sandbox, env, SSRF, --tools, awk/sed)."""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

import tether.sandbox as sb_mod
from tether import Harness, SandboxPolicy, SandboxViolationError
from tether.tools.web import PrivateAddressError, assert_public_url

needs_bwrap = pytest.mark.skipif(not sb_mod._can_use_bwrap(), reason="bwrap unavailable")


def test_scrub_env_is_allowlist(tmp_path: Path) -> None:
    sb = SandboxPolicy(workspace_root=tmp_path)
    base = {"PATH": "/bin", "LC_ALL": "C", "DATABASE_URL": "x", "MY_KEY": "y", "SLACK_WEBHOOK": "z"}
    env = sb.scrub_env(base)
    assert env["PATH"] == "/bin" and env["LC_ALL"] == "C"
    assert not {"DATABASE_URL", "MY_KEY", "SLACK_WEBHOOK"} & env.keys()
    env = sb.scrub_env({**base, "TETHER_ENV_PASSTHROUGH": "DATABASE_URL"})
    assert env["DATABASE_URL"] == "x" and "MY_KEY" not in env


def test_network_flag_roundtrip_and_attenuation(tmp_path: Path) -> None:
    sb = SandboxPolicy(workspace_root=tmp_path, network=False)
    assert SandboxPolicy.from_dict(sb.to_dict()).network is False
    assert sb.attenuate().network is False
    assert SandboxPolicy(workspace_root=tmp_path).attenuate(child_network=False).network is False
    assert sb.attenuate(child_network=True).network is False  # never widens


async def test_no_network_fails_closed_without_bwrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    with pytest.raises(SandboxViolationError, match="network isolation"):
        await SandboxPolicy(workspace_root=tmp_path, network=False).execute_bash("echo hi")


def test_protected_mounts_mask_nested_secrets(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    for name in ("sub/.env", "sub/server.pem", "k.key", "plain.txt"):
        (tmp_path / name).write_text("s")
    args = SandboxPolicy(workspace_root=tmp_path)._protected_mounts()
    for masked in ("sub/.env", "sub/server.pem", "k.key"):
        assert str(tmp_path / masked) in args
    assert str(tmp_path / "plain.txt") not in args


@needs_bwrap
async def test_bwrap_masks_nested_secret_and_hides_var_tmp(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".env").write_text("CANARY")
    code, out = await SandboxPolicy(workspace_root=tmp_path).execute_bash_with_code(
        "cat sub/.e''nv; python3 -c \"import os;print(os.listdir('/var/tmp'))\""
    )
    assert "CANARY" not in out and "[]" in out


@needs_bwrap
async def test_bwrap_no_network_blocks_loopback(tmp_path: Path) -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    py = f"import socket;socket.create_connection(('127.0.0.1',{port}),2);print('CONNECTED')"
    cmd = f'python3 -c "{py}"'
    _, out = await SandboxPolicy(workspace_root=tmp_path).execute_bash_with_code(cmd)
    assert "CONNECTED" in out
    _, out = await SandboxPolicy(workspace_root=tmp_path, network=False).execute_bash_with_code(cmd)
    assert "CONNECTED" not in out
    srv.close()


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/x", "http://[::1]/", "http://10.0.0.5/", "http://169.254.169.254/"]
)
async def test_web_fetch_blocks_private_addresses(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TETHER_WEB_ALLOW_PRIVATE", raising=False)
    with pytest.raises(PrivateAddressError):
        await assert_public_url(httpx.Request("GET", url))
    monkeypatch.setenv("TETHER_WEB_ALLOW_PRIVATE", "1")
    await assert_public_url(httpx.Request("GET", url))


@pytest.mark.parametrize(
    "cmd",
    [
        "awk '/^# P/{n++} END{print n}' README.md",
        "sed -n '/^## M/p' README.md",
        "sed -n '/error/d' README.md",
        "grep -c /etc/passwd README.md",
        "cd . && awk '/a/{n++}' README.md",
    ],
)
def test_program_args_are_not_paths(cmd: str, tmp_path: Path) -> None:
    SandboxPolicy(workspace_root=tmp_path).validate_bash_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    ["sed -n p /etc/hosts", "awk -f /etc/passwd x", "cat /etc/hosts", "cd . && cat /etc/hosts"],
)
def test_real_absolute_paths_still_blocked(cmd: str, tmp_path: Path) -> None:
    with pytest.raises(SandboxViolationError):
        SandboxPolicy(workspace_root=tmp_path).validate_bash_command(cmd)


def test_unknown_tool_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bahs"):
        Harness(tools="bash,bahs", db_path=tmp_path / "t.db")
    Harness(tools="all", db_path=tmp_path / "t.db")


def test_host_socket_masks_are_ro_bind_triples() -> None:
    args = sb_mod._host_socket_masks()
    assert len(args) % 3 == 0
    assert all(args[i : i + 2] == ("--ro-bind", "/dev/null") for i in range(0, len(args), 3))


async def test_web_fetch_tool_reports_blocked_and_mapped_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tether.tools.web import make_web_tool

    monkeypatch.delenv("TETHER_WEB_ALLOW_PRIVATE", raising=False)
    tool = make_web_tool()
    out = await tool.fn(["fetch", "http://[::ffff:127.0.0.1]/"])
    assert out.startswith("Error: blocked")


async def test_cli_rejects_unknown_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tether.cli import _async_main

    monkeypatch.chdir(tmp_path)
    rc = await _async_main(["run", "--tools", "bahs", "--db", str(tmp_path / "t.db"), "hello"])
    assert rc == 1
