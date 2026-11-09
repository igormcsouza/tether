"""Allowlist of commands that run outside the jail (#59, #124 item 4). Fakes only, no network."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy, SandboxViolationError


class _FakeProc:
    def __init__(self, stdout: bytes, hang: bool) -> None:
        self.pid = 4242
        self.returncode = 0
        self._stdout = stdout
        self._hang = hang

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(3600)
        return self._stdout, b""

    async def wait(self) -> int:
        return self.returncode


class _Runs:
    """Every subprocess the sandbox starts; argv[0] == "bwrap" means it was jailed."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.stdout = b"ok\n"
        self.hang = False

    def outside(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["argv"][0] != "bwrap"]


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> _Runs:
    rec = _Runs()

    async def fake_exec(*argv: str, **kwargs: Any) -> _FakeProc:
        rec.calls.append({"argv": list(argv), "env": kwargs.get("env"), "cwd": kwargs.get("cwd")})
        return _FakeProc(rec.stdout, rec.hang)

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    monkeypatch.setattr(sb_mod.asyncio, "create_subprocess_exec", fake_exec)
    # The timeout path SIGKILLs a process group; the fake pid must never reach a real killpg.
    monkeypatch.setattr(sb_mod.os, "killpg", lambda pid, sig: None)
    return rec


async def test_prefix_match_is_by_token(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push",))
    await policy.execute_bash("git push origin main")
    await policy.execute_bash("git  push origin main")
    await policy.execute_bash("git pushx")
    await policy.execute_bash("git commit -m x")
    await policy.execute_bash("echo hi")
    assert [c["argv"] for c in runs.outside()] == [
        ["git", "push", "origin", "main"],
        ["git", "push", "origin", "main"],
    ]
    assert len(runs.calls) == 5


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main;rm x",
        "git push;rm x",
        "git push && id",
        "git push || id",
        "git push | cat",
        "git push $(id)",
        "git push `id`",
        "git push > f",
        "git push < f",
        "git push\nid",
        "git push &",
    ],
)
async def test_metacharacters_never_run_outside(tmp_path: Path, runs: _Runs, cmd: str) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push",))
    with pytest.raises(SandboxViolationError, match="Instead:"):
        await policy.execute_bash(cmd)
    assert runs.calls == []


async def test_outside_env_is_scrubbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs: _Runs
) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-999")
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push",))
    await policy.execute_bash("git push origin main")
    (call,) = runs.outside()
    assert "AWS_SECRET_ACCESS_KEY" not in call["env"]
    assert call["cwd"] == str(policy.workspace_root)
    assert call["env"]["HOME"] == os.path.expanduser("~")


async def test_outside_timeout_and_output_cap(tmp_path: Path, runs: _Runs) -> None:
    slow = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push",), timeout_seconds=0.05)
    runs.hang = True
    code, out = await slow.execute_bash_with_code("git push origin main")
    assert code == 124
    assert "timed out" in out
    runs.hang = False
    runs.stdout = ("x" * 5000).encode()
    capped = SandboxPolicy(
        workspace_root=tmp_path, allow_outside=("git push",), max_output_chars=1000
    )
    assert "by sandbox cap" in await capped.execute_bash("git push origin main")


async def test_allow_file_loaded_and_protected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs: _Runs
) -> None:
    (tmp_path / ".tether").mkdir()
    allow_file = tmp_path / ".tether" / "allow.json"
    allow_file.write_text(json.dumps({"allow": ["git push", "gh"]}))
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("gh",))
    assert policy.with_allow_file().allow_outside == ("git push", "gh")
    assert policy.allow_outside == ("gh",)  # the caller's object is never mutated

    for bad in ("{not json", json.dumps({"allow": "git"}), json.dumps({"allow": [1]})):
        allow_file.write_text(bad)
        with pytest.raises(ValueError, match="allow.json"):
            policy.with_allow_file()
    allow_file.write_text(json.dumps({"allow": []}))
    assert SandboxPolicy(workspace_root=tmp_path).with_allow_file().allow_outside == ()

    # The model must not read or write its own permissions, jailed or not.
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    mounts = policy._protected_mounts()
    hidden = str(policy.workspace_root / ".tether")
    assert mounts[mounts.index(hidden) - 1] == "--tmpfs"
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", False)
    with pytest.raises(SandboxViolationError, match="tether"):
        policy.validate_bash_command("cat .tether/allow.json")
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    git_policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    with pytest.raises(SandboxViolationError, match="tether"):
        await git_policy.execute_bash("git show HEAD:.tether/allow.json")
    assert runs.outside() == []


def test_children_only_narrow(tmp_path: Path) -> None:
    parent = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push", "gh"))
    assert parent.attenuate().allow_outside == ("git push", "gh")
    assert parent.attenuate(child_allow_outside=["gh", "docker"]).allow_outside == ("gh",)
    assert parent.attenuate(child_allow_outside=[]).allow_outside == ()
    narrow = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    assert narrow.attenuate(child_allow_outside=["git push"]).allow_outside == ()
    assert parent.to_dict()["allow_outside"] == ["git push", "gh"]
    assert SandboxPolicy.from_dict(parent.to_dict()).allow_outside == ("git push", "gh")


def test_parse_allow_outside_normalises_and_rejects() -> None:
    assert sb_mod.parse_allow_outside(["git  push", "git push", "gh"]) == ("git push", "gh")
    assert sb_mod.parse_allow_outside(None) == ()
    for bad in ("", "   ", "git push;rm", "gh && id", "gh|cat"):
        with pytest.raises(ValueError):
            sb_mod.parse_allow_outside([bad])


def test_cli_allow_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tether import cli as cli_mod

    seen: list[SandboxPolicy] = []

    class _Stop(Exception):
        pass

    def fake_harness(*args: Any, **kwargs: Any) -> None:
        seen.extend(v for v in (*args, *kwargs.values()) if isinstance(v, SandboxPolicy))
        raise _Stop

    monkeypatch.setattr(cli_mod, "Harness", fake_harness)
    with pytest.raises(_Stop):
        cli_mod.main(["run", "--allow", "git push", "--allow", "gh", "task"])
    assert seen[0].allow_outside == ("git push", "gh")
    assert cli_mod.main(["run", "--allow", "a;b", "task"]) == cli_mod.EXIT_USAGE
    assert "Error: --allow" in capsys.readouterr().err
    assert cli_mod.main(["run", "--allow", "", "task"]) == cli_mod.EXIT_USAGE
    assert "Error: --allow" in capsys.readouterr().err


async def test_read_only_profile_never_runs_outside(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(
        profile="read-only", workspace_root=tmp_path, allow_outside=("git push",)
    )
    with pytest.raises(SandboxViolationError):
        await policy.execute_bash("git push origin main")
    assert runs.outside() == []


async def test_no_network_refuses_outside_run(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, network=False, allow_outside=("git push",))
    with pytest.raises(SandboxViolationError, match="--no-network"):
        await policy.execute_bash("git push origin main")
    assert runs.calls == []


async def test_unbalanced_quotes_refused(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push",))
    with pytest.raises(SandboxViolationError, match="unbalanced"):
        await policy.execute_bash("git push 'x")
    assert runs.calls == []


async def test_leading_space_and_stdin_only_match(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git push",))
    await policy.execute_bash("   git push origin main")
    await policy.execute_bash("", stdin="git push origin main")
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]] * 2


def test_allow_file_entry_with_metacharacter_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".tether").mkdir()
    (tmp_path / ".tether" / "allow.json").write_text(json.dumps({"allow": ["git;rm"]}))
    with pytest.raises(ValueError, match="allow.json.*metacharacter"):
        sb_mod.load_allow_file(tmp_path)


def test_pipeline_allow_flag_and_bad_allow_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tether import cli as cli_mod

    assert cli_mod.main(["pipeline", "p.yaml", "task", "--allow", "a;b"]) == cli_mod.EXIT_USAGE
    assert "Error: --allow" in capsys.readouterr().err

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".tether").mkdir()
    (tmp_path / ".tether" / "allow.json").write_text("{not json")
    db = str(tmp_path / "t.db")
    assert cli_mod.main(["pipeline", "p.yaml", "task", "--db", db]) == 1
    assert "allow.json" in capsys.readouterr().err


async def _jailed(policy: SandboxPolicy, cmd: str) -> None:
    try:
        await policy.execute_bash(cmd)
    except SandboxViolationError:
        pass


@pytest.mark.parametrize(
    "cmd",
    [
        "git push --receive-pack=sh x",
        "git push --receive-pack sh x",
        "git -C/etc status",
        "git -C /etc status",
        "git -c core.sshCommand=x fetch",
        "git -ccore.x=y push",
        "git push --exec-path=/tmp x",
        "git push --upload-pack=sh x",
        "git push --git-dir=/etc x",
        "git push --work-tree=/etc x",
        "git push --namespace=x x",
    ],
)
async def test_git_unsafe_options_stay_jailed(tmp_path: Path, runs: _Runs, cmd: str) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    await _jailed(policy, cmd)
    assert runs.outside() == []


async def test_plain_git_push_still_runs_outside(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    await policy.execute_bash("git push origin main")
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]


@pytest.mark.parametrize(
    "cmd",
    [
        "git config --global user.name x",
        "git config user.name x",
        "git config --list",
        "git config core.sshCommand x",
        "git config core.hooksPath hk",
        "git config core.fsmonitor x",
        "git config core.pager x",
        "git config core.editor x",
        "git config credential.helper x",
        "git config alias.x !sh",
        "git config url.x.insteadOf y",
        "git config include.path x",
        "git config includeIf.gitdir:/x.path y",
        "git config http.proxy x",
        "git config http.https://h.example/.proxy x",
        "git config gpg.program x",
        "git remote add origin https://example.com/x.git",
        "git remote set-url origin https://example.com/x.git",
        "git remote set-head origin main",
        "git submodule update --init",
    ],
)
async def test_bare_git_entry_never_covers_config_remote_submodule(
    tmp_path: Path, runs: _Runs, cmd: str
) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    await _jailed(policy, cmd)
    assert runs.outside() == []


@pytest.mark.parametrize(
    ("entry", "cmd"),
    [
        ("git config user.name", "git config user.name x"),
        ("git config", "git config user.name x"),
        ("git remote add", "git remote add origin https://example.com/x.git"),
        ("git submodule update", "git submodule update --init"),
        ("git remote set-url", "git remote set-url origin https://example.com/x.git"),
        ("git submodule", "git submodule add https://example.com/x.git"),
    ],
)
async def test_explicit_git_subcommand_entry_runs_outside(
    tmp_path: Path, runs: _Runs, entry: str, cmd: str
) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=(entry,))
    await policy.execute_bash(cmd)
    assert [c["argv"] for c in runs.outside()] == [cmd.split()]


@pytest.mark.parametrize(
    ("entry", "cmd"),
    [
        ("git config", "git config core.sshCommand x"),
        ("git config core.sshCommand", "git config core.sshCommand x"),
        ("git config alias", "git config alias.x !sh"),
        ("git config core.hooksPath", "git config core.hooksPath hk"),
        ("git config gpg.program", "git config gpg.program x"),
        ("git config http.proxy", "git config http.proxy x"),
        ("git remote", "git remote set-url origin https://example.com/x.git"),
        ("git remote", "git remote add origin https://example.com/x.git"),
    ],
)
async def test_explicit_entry_still_jails_risky_config_keys(
    tmp_path: Path, runs: _Runs, entry: str, cmd: str
) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=(entry,))
    await _jailed(policy, cmd)
    assert runs.outside() == []


async def test_bare_git_entry_still_runs_remote_list_outside(tmp_path: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, allow_outside=("git",))
    await policy.execute_bash("git remote -v")
    assert [c["argv"] for c in runs.outside()] == [["git", "remote", "-v"]]


def test_git_jailed_helper_edges() -> None:
    from tether.sandbox import _git_jailed

    assert _git_jailed([], ["git"]) is False
    assert _git_jailed(["gh", "config"], ["gh"]) is False
    assert _git_jailed(["git", "--version"], ["git"]) is False
    assert _git_jailed(["git", "-C", "x"], ["git"]) is False
    assert _git_jailed(["git", "remote", "-v"], ["git", "remote"]) is False
    assert _git_jailed(["git", "config", "user.name", "x"], ["git"]) is True
    assert _git_jailed(["git", "config", "user.name", "x"], ["git", "config"]) is False
