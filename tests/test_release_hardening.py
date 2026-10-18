"""Regression tests found while validating the v0.1.0 release candidate."""

from __future__ import annotations

from pathlib import Path

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy, SQLiteStore
from tether.cli import _async_main


def test_protected_mounts_mask_sensitive_paths(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("K=1")
    (tmp_path / ".env.local").write_text("K=2")
    (tmp_path / ".tether").mkdir()
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / ".git" / "config").write_text("cfg")
    args = SandboxPolicy(workspace_root=tmp_path)._protected_mounts()
    for masked in (".env", ".env.local", ".git/config"):
        assert ["--ro-bind", "/dev/null", str(tmp_path / masked)] == [
            *args[args.index(str(tmp_path / masked)) - 2 : args.index(str(tmp_path / masked)) + 1]
        ]
    assert ["--tmpfs", str(tmp_path / ".tether")] == [
        *args[args.index(str(tmp_path / ".tether")) - 1 : args.index(str(tmp_path / ".tether")) + 1]
    ]
    assert str(tmp_path / ".git" / "hooks") in args
    assert SandboxPolicy(workspace_root=tmp_path / "nowhere")._protected_mounts() == []


def test_scrub_env_drops_ssh_agent(tmp_path: Path) -> None:
    env = SandboxPolicy(workspace_root=tmp_path).scrub_env(
        {"SSH_AUTH_SOCK": "/run/user/1/s", "PATH": "/bin"}
    )
    assert "SSH_AUTH_SOCK" not in env
    assert env["PATH"] == "/bin"


async def test_bwrap_blocks_glob_access_to_protected_files(tmp_path: Path) -> None:
    if not sb_mod._can_use_bwrap():
        pytest.skip("bwrap unavailable")
    (tmp_path / ".env").write_text("SECRET=1")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("cfg")
    sandbox = SandboxPolicy(workspace_root=tmp_path)
    code, out = await sandbox.execute_bash_with_code("cat .e*")
    assert code != 0 and "SECRET" not in out
    code, _ = await sandbox.execute_bash_with_code("echo pwn >> .git/con*")
    assert code != 0
    assert (tmp_path / ".git" / "config").read_text() == "cfg"


def test_stats_ignore_pipeline_root_sessions(tmp_path: Path) -> None:
    store = SQLiteStore(db_path=tmp_path / "t.db")
    root = store.create_session(
        goal="p", model="ollama/default", sandbox_config={"pipeline": {"stages": []}}
    )
    store.update_session(root.id, status="COMPLETED", add_prompt_tokens=99)
    assert store.get_stats().models == []
    stage = store.create_session(goal="s", model="ollama/real", parent_id=root.id)
    store.update_session(stage.id, status="COMPLETED", add_prompt_tokens=99)
    assert [m.model for m in store.get_stats().models] == ["ollama/real"]


async def test_cli_reports_bad_pipeline_and_unknown_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "t.db")
    bad = tmp_path / "bad.yaml"
    bad.write_text("stages: [")
    assert await _async_main(["pipeline", str(bad), "--db", db, "g"]) == 1
    assert await _async_main(["pipeline", str(tmp_path / "missing.yaml"), "--db", db, "g"]) == 1
    empty = tmp_path / "empty.yaml"
    empty.write_text("stages:\n  - id: a\n")
    assert await _async_main(["pipeline", str(empty), "--db", db, "g"]) == 1
    assert await _async_main(["send", "ses_nope", "hi", "--db", db]) == 1
    err = capsys.readouterr().err
    assert err.count("Error:") == 4 and "Traceback" not in err


def test_bwrap_argv_unshares_pid_and_ipc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: True)
    argv = SandboxPolicy(workspace_root=tmp_path)._build_exec_argv("true")
    assert "--unshare-pid" in argv and "--unshare-ipc" in argv


async def test_unknown_command_hints_bash_only_when_enabled() -> None:
    from tether.multiplexer import Multiplexer
    from tether.tools.bash import make_bash_tool

    mux = Multiplexer()
    assert "bash" not in (await mux.execute("echo hi")).output
    mux.register(make_bash_tool(SandboxPolicy()))
    assert "`bash echo hi`" in (await mux.execute("echo hi")).output
