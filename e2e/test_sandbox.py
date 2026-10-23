"""Deterministic security envelope (Rule 6). The proxy forces the dangerous action, so the
result never depends on the model's obedience; tether alone must say no."""

from __future__ import annotations

import shutil

import pytest

from e2e.conftest import Tether


def test_edit_cannot_write_outside_the_workspace(tether: Tether, chaos) -> None:
    chaos.script(("edit write ../escape.txt", "pwned"), ("done", "ok"))
    r = tether.run("escape", "--tools", "edit")
    out = tether.tool_outputs(r["id"])[0]
    assert "outside" in out.lower() or "workspace" in out.lower(), out
    assert not (tether.ws.parent / "escape.txt").exists()


def test_secret_and_internal_files_are_protected(tether: Tether, chaos) -> None:
    chaos.script(("edit write .env", "KEY=1"), ("edit write .tether/x", "1"), ("done", "ok"))
    r = tether.run("write secrets", "--tools", "edit")
    outs = tether.tool_outputs(r["id"])[:2]
    assert all("Error" in o or "protected" in o.lower() or "denied" in o.lower() for o in outs), (
        outs
    )
    assert not (tether.ws / ".env").exists() and not (tether.ws / ".tether" / "x").exists()


def test_bash_environment_is_scrubbed(tether: Tether, chaos) -> None:
    chaos.script("bash env", ("done", "ok"))
    r = tether.run("show env", "--tools", "bash")
    env_out = tether.tool_outputs(r["id"])[0]
    assert "sekret-value-123" not in env_out and "E2E_KEY" not in env_out, env_out


def test_web_fetch_blocks_loopback_ssrf(tether: Tether, chaos) -> None:
    chaos.script(
        "web fetch http://127.0.0.1:9/",
        "web fetch http://169.254.169.254/latest/meta-data",
        ("done", "ok"),
    )
    r = tether.run("fetch internal", "--tools", "web")
    outs = tether.tool_outputs(r["id"])[:2]
    assert all(
        "block" in o.lower() or "private" in o.lower() or "loopback" in o.lower() for o in outs
    ), outs


def test_read_only_profile_refuses_writes(tether: Tether, chaos) -> None:
    chaos.script(("edit write a.txt", "x"), ("done", "ok"))
    r = tether.run("write", "--tools", "edit", "--sandbox", "read-only")
    assert not (tether.ws / "a.txt").exists(), tether.tool_outputs(r["id"])


def test_verify_gate_can_run_a_tool_installed_under_home(tether: Tether, chaos) -> None:
    home_bin = tether.home / ".local" / "bin"
    home_bin.mkdir(parents=True)
    tool = home_bin / "gatetool"
    tool.write_text("#!/bin/sh\necho gate-ok\n")
    tool.chmod(0o755)
    tether.env["PATH"] = f"{home_bin}:{tether.env['PATH']}"
    chaos.script(("done", "ok"))
    d = tether.run("x", "--verify", "gatetool", "--tools", "bash")
    assert d["rc"] == 0, d


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bwrap")
def test_bash_reads_env_template_but_not_the_secret(tether: Tether, chaos) -> None:
    (tether.ws / ".env").write_text("TOKEN=hunter2")
    (tether.ws / ".env.example").write_text("TOKEN=\n")
    chaos.script("bash cat .env.example", "bash cat .env", ("done", "ok"))
    r = tether.run("read env files", "--tools", "bash")
    template, secret = tether.tool_outputs(r["id"])[:2]
    assert "TOKEN=" in template and "Sandbox violation" not in template, template
    assert "hunter2" not in secret, secret  # masked by the kernel mount, not by a text rule
