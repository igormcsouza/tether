"""Escalation: ask the caller once, then remember (#59, #124 item 4). Fakes only, no network.

The model runs a command whose prefix is in the policy's `escalate` list and not allowlisted.
The session pauses as WAITING_INPUT with `[APPROVAL NEEDED]`. Only the caller (`Harness.send`,
CLI `send`/`allow`, MCP `tether_send`) can approve it.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import tether.harness as harness_mod
import tether.sandbox as sb_mod
from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, SandboxPolicy, SandboxViolationError, api
from tether import cli as cli_mod
from tether.mcp import TetherMCP
from tether.store import SQLiteStore
from tether.tools.bash import make_bash_tool

PUSH = "git push origin main"
PENDING = {"command": PUSH, "prefix": "git push"}


class _FakeProc:
    def __init__(self, stdout: bytes) -> None:
        self.pid = 4242
        self.returncode = 0
        self._stdout = stdout

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        return self._stdout, b""

    async def wait(self) -> int:
        return self.returncode


class _Runs:
    """Every subprocess the sandbox starts; argv[0] == "bwrap" means it was jailed."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.stdout = b"pushed-ok\n"

    def outside(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["argv"][0] != "bwrap"]

    def jailed(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["argv"][0] == "bwrap"]


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> _Runs:
    rec = _Runs()

    async def fake_exec(*argv: str, **kwargs: Any) -> _FakeProc:
        rec.calls.append({"argv": list(argv), "cwd": kwargs.get("cwd")})
        return _FakeProc(rec.stdout)

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    monkeypatch.setattr(sb_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(sb_mod.os, "killpg", lambda pid, sig: None)
    return rec


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path.resolve()


def _bash(cmd: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd="bash", stdin=cmd))


def _done(text: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd="done", stdin=text))


def _policy(ws: Path, **kw: Any) -> SandboxPolicy:
    try:
        return SandboxPolicy(workspace_root=ws, **kw)
    except TypeError as exc:  # the field does not exist yet
        pytest.fail(f"SandboxPolicy does not accept {sorted(kw)}: {exc}")


def _harness(tmp_path: Path, ws: Path, provider: Any, **kw: Any) -> Harness:
    kw.setdefault("tools", ["bash"])
    kw.setdefault("sandbox", SandboxPolicy(workspace_root=ws))
    return Harness(provider=provider, db_path=tmp_path / "t.db", **kw)


def _last_prompt(provider: FakeScriptedProvider) -> str:
    return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[-1])


def _allow(ws: Path) -> Any:
    return json.loads((ws / ".tether" / "allow.json").read_text())


async def _paused(tmp_path: Path, ws: Path, runs: _Runs, *more: ModelResponse) -> Any:
    provider = FakeScriptedProvider([_bash(PUSH), *more])
    h = _harness(tmp_path, ws, provider)
    rec = await h.run("push the branch")
    assert rec.status == "WAITING_INPUT", f"no pause; ran {runs.calls}, result {rec.result!r}"
    return h, provider, rec


# DoD-1
async def test_unlisted_command_pauses_for_approval(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    provider = FakeScriptedProvider([_bash(PUSH), _done("pushed")])
    rec = await _harness(tmp_path, ws, provider).run("push the branch")
    assert rec.status == "WAITING_INPUT"
    assert api.exit_code(rec) == 2
    assert (rec.result or "").startswith("[APPROVAL NEEDED]")
    assert PUSH in (rec.result or "")
    assert "`git push`" in (rec.result or "")
    assert f"tether send {rec.id} approve" in (rec.result or "")
    assert runs.calls == []  # nothing ran, jailed or not
    assert not (ws / ".tether" / "allow.json").exists()


# DoD-2
async def test_approve_adds_prefix_and_resumes(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    h, provider, rec = await _paused(tmp_path, ws, runs, _done("pushed"))
    resumed = await h.send(rec.id, "approve")
    assert _allow(ws) == {"allow": ["git push"]}
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]
    assert runs.outside()[0]["cwd"] == str(ws)
    prompt = _last_prompt(provider)
    assert "pushed-ok" in prompt
    assert "approved" in prompt and "allow.json" in prompt
    assert resumed.status == "COMPLETED" and resumed.result == "pushed"
    assert resumed.step_count == 2  # the approved run is not a model step
    assert "approval" not in resumed.sandbox_config


# DoD-3
async def test_approved_prefix_does_not_ask_again(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    h, _, rec = await _paused(tmp_path, ws, runs, _bash("git push origin x"), _done("ok"))
    resumed = await h.send(rec.id, "approve")
    assert resumed.status == "COMPLETED"
    assert [c["argv"] for c in runs.outside()] == [
        ["git", "push", "origin", "main"],
        ["git", "push", "origin", "x"],
    ]
    # A new session in the same workspace reads .tether/allow.json and does not ask.
    provider2 = FakeScriptedProvider([_bash("git push origin y"), _done("again")])
    again = await _harness(tmp_path, ws, provider2).run("push again")
    assert again.status == "COMPLETED" and again.result == "again"
    assert runs.outside()[-1]["argv"] == ["git", "push", "origin", "y"]
    assert runs.jailed() == []


# DoD-4
@pytest.mark.parametrize("reply", ["deny", "no, use a PR"])
async def test_deny_runs_nothing(tmp_path: Path, ws: Path, runs: _Runs, reply: str) -> None:
    h, provider, rec = await _paused(tmp_path, ws, runs, _done("opened a PR"))
    resumed = await h.send(rec.id, reply)
    assert not (ws / ".tether" / "allow.json").exists()
    assert runs.calls == []
    prompt = _last_prompt(provider)
    assert "did not allow" in prompt and PUSH in prompt and "nothing ran" in prompt
    assert reply in prompt
    assert resumed.status == "COMPLETED" and resumed.result == "opened a PR"
    assert "approval" not in resumed.sandbox_config


# DoD-5a
@pytest.mark.parametrize("cmd", ["git status", "git diff", "git log", "git show HEAD"])
async def test_read_only_git_not_escalated(tmp_path: Path, ws: Path, runs: _Runs, cmd: str) -> None:
    provider = FakeScriptedProvider([_bash(cmd), _done("looked")])
    h = _harness(tmp_path, ws, provider)
    assert "git push" in getattr(h.sandbox, "escalate", ()), "no default escalate list"
    rec = await h.run("look around")
    assert rec.status == "COMPLETED"
    assert len(runs.jailed()) == 1 and runs.outside() == []
    assert runs.jailed()[0]["argv"][-1] == cmd
    assert "approval" not in api.session_dict(rec)


# DoD-5b
@pytest.mark.parametrize("cmd", ["git push; rm x", "gh pr list | cat", "docker $(id)"])
async def test_metacharacter_commands_not_escalated(
    tmp_path: Path, ws: Path, runs: _Runs, cmd: str
) -> None:
    provider = FakeScriptedProvider([_bash(cmd), _done("gave up")])
    rec = await _harness(tmp_path, ws, provider).run("do it")
    assert runs.calls == []  # refused, not silently jailed
    prompt = _last_prompt(provider)
    assert "metacharacters" in prompt and "Instead:" in prompt
    assert "[APPROVAL NEEDED]" not in prompt
    assert rec.status == "COMPLETED"
    assert "approval" not in rec.sandbox_config


# DoD-6 (sync: cli.main runs its own event loop)
def test_foreground_run_exits_2_with_request(
    tmp_path: Path,
    ws: Path,
    runs: _Runs,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FakeScriptedProvider([_bash(PUSH), _done("pushed")])
    monkeypatch.setattr(harness_mod, "resolve_provider", lambda *a, **k: provider)
    monkeypatch.chdir(ws)
    rc = cli_mod.main(["run", "--tools", "bash", "--db", str(tmp_path / "t.db"), "push it"])
    out, err = capsys.readouterr()
    assert rc == 2
    assert "[APPROVAL NEEDED]" in err and PUSH in err
    assert "tether send" in err and "approve" in err and "deny" in err
    assert out == ""
    assert runs.calls == []


# DoD-7
async def test_child_escalation_visible_on_child(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    parent_provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd="agent spawn --tools bash push it")),
            _done("spawned"),
        ]
    )
    parent_h = _harness(
        tmp_path, ws, parent_provider, tools=["bash", "agent"], worker_spawner=lambda sid: None
    )
    parent = await parent_h.run("delegate the push")
    assert parent.status == "COMPLETED"
    store = SQLiteStore(db_path=tmp_path / "t.db")
    (child,) = [s for s in store.list_sessions(limit=10) if s.parent_id == parent.id]
    assert "git push" in child.sandbox_config.get("escalate", []), "escalate not inherited"

    child_provider = FakeScriptedProvider([_bash(PUSH), _done("child pushed")])
    child_h = Harness(provider=child_provider, db_path=tmp_path / "t.db")
    paused = await child_h.execute_session(child.id)
    assert paused.status == "WAITING_INPUT"
    assert api.session_dict(paused).get("approval") == PENDING
    assert runs.calls == []
    resumed = await child_h.send(child.id, "approve")
    assert resumed.status == "COMPLETED" and resumed.result == "child pushed"
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]
    assert _allow(ws) == {"allow": ["git push"]}


# DoD-8
async def test_json_view_has_pending_approval(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    h, _, rec = await _paused(tmp_path, ws, runs, _done("refused"))
    mcp = TetherMCP(db_path=tmp_path / "t.db", workspace=ws)
    assert api.session_dict(rec).get("approval") == PENDING
    assert (await mcp.call("tether_status", {"id": rec.id})).get("approval") == PENDING
    assert (await mcp.call("tether_read", {"id": rec.id})).get("approval") == PENDING
    resumed = await h.send(rec.id, "deny")
    assert "approval" not in api.session_dict(resumed)
    assert "approval" not in await mcp.call("tether_status", {"id": rec.id})


# Bad day: the model's `agent send` path writes the inbox directly; that never approves.
async def test_agent_send_approve_does_not_approve(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    h, provider, rec = await _paused(tmp_path, ws, runs, _done("refused"))
    h.store.enqueue_inbox(rec.id, "approve")
    h.store.update_session(rec.id, status="PENDING")  # what `agent send` does
    resumed = await h.execute_session(rec.id)
    assert not (ws / ".tether" / "allow.json").exists()
    assert runs.calls == []
    assert "did not allow" in _last_prompt(provider)
    assert resumed.status == "COMPLETED"


@pytest.mark.parametrize("kw", [{"profile": "read-only"}, {"network": False}])
async def test_read_only_and_no_network_never_offer(
    ws: Path, runs: _Runs, kw: dict[str, Any]
) -> None:
    policy = SandboxPolicy(workspace_root=ws, **kw)
    assert "git push" in getattr(policy, "escalate", ()), "no default escalate list"
    try:
        await policy.execute_bash(PUSH)
    except SandboxViolationError as exc:
        assert "[APPROVAL NEEDED]" not in str(exc)
    assert runs.outside() == []


@pytest.mark.parametrize(
    "cmd", ["git -c core.sshCommand=x push origin main", "git -C /tmp push origin main"]
)
async def test_git_unsafe_option_not_offered(ws: Path, runs: _Runs, cmd: str) -> None:
    policy = SandboxPolicy(workspace_root=ws)
    assert "git push" in getattr(policy, "escalate", ()), "no default escalate list"
    try:
        await policy.execute_bash(cmd)
    except SandboxViolationError as exc:
        assert "[APPROVAL NEEDED]" not in str(exc)
    assert runs.outside() == []


async def test_malformed_allow_file_on_approve_is_loud(
    tmp_path: Path, ws: Path, runs: _Runs
) -> None:
    h, _, rec = await _paused(tmp_path, ws, runs, _done("stopped"))
    (ws / ".tether").mkdir()
    bad = ws / ".tether" / "allow.json"
    bad.write_text("{not json")
    resumed = await h.send(rec.id, "approve")  # must not raise
    text = "\n".join([resumed.result or "", *(t.content or "" for t in h.store.get_turns(rec.id))])
    assert ".tether/allow.json:" in text
    assert "Traceback" not in text
    assert runs.calls == []
    assert bad.read_text() == "{not json"


def test_add_to_allow_file_keeps_entries(tmp_path: Path) -> None:
    add = getattr(sb_mod, "add_to_allow_file", None)
    assert callable(add), "tether.sandbox.add_to_allow_file is missing"
    add(tmp_path, "git push")  # creates .tether/ when missing
    assert _allow(tmp_path) == {"allow": ["git push"]}
    (tmp_path / ".tether" / "allow.json").write_text(json.dumps({"allow": ["gh", "git push"]}))
    add(tmp_path, "git push")
    assert _allow(tmp_path) == {"allow": ["gh", "git push"]}
    add(tmp_path, "docker")
    assert _allow(tmp_path) == {"allow": ["gh", "git push", "docker"]}
    (tmp_path / ".tether" / "allow.json").write_text("{not json")
    with pytest.raises(ValueError, match=r"\.tether/allow\.json:"):
        add(tmp_path, "gh")
    assert (tmp_path / ".tether" / "allow.json").read_text() == "{not json"


async def test_custom_escalate_list(ws: Path, runs: _Runs) -> None:
    policy = _policy(ws, escalate=("make  deploy",))
    assert policy.escalate == ("make deploy",)  # normalised like allow_outside
    with pytest.raises(SandboxViolationError, match=r"^\[APPROVAL NEEDED\] make deploy prod") as e:
        await policy.execute_bash("make deploy prod")
    assert isinstance(e.value, sb_mod.ApprovalNeeded)
    assert e.value.command == "make deploy prod"
    assert e.value.prefix == sb_mod.approval_prefix(["make", "deploy", "prod"])
    await policy.execute_bash(PUSH)  # not in this list: stays jailed, no pause
    assert [c["argv"][0] for c in runs.calls] == ["bwrap"]


def test_escalate_roundtrip_and_inherited(ws: Path) -> None:
    assert getattr(sb_mod, "DEFAULT_ESCALATE", None) == (
        "git push",
        "git pull",
        "git fetch",
        "git clone",
        "git worktree",
        "git config",
        "gh",
        "docker",
    )
    policy = _policy(ws, escalate=("gh",))
    assert policy.to_dict()["escalate"] == ["gh"]
    assert SandboxPolicy.from_dict(policy.to_dict()).escalate == ("gh",)
    legacy = {k: v for k, v in policy.to_dict().items() if k != "escalate"}
    assert SandboxPolicy.from_dict(legacy).escalate == sb_mod.DEFAULT_ESCALATE
    assert policy.attenuate().escalate == ("gh",)
    assert sb_mod.approval_prefix(["git", "push", "origin"]) == "git push"
    assert sb_mod.approval_prefix(["gh", "pr", "create"]) == "gh"
    with pytest.raises(ValueError):
        _policy(ws, escalate=("gh;id",))


def test_cli_allow_subcommand(
    tmp_path: Path,
    ws: Path,
    runs: _Runs,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FakeScriptedProvider([_bash(PUSH), _done("pushed")])
    monkeypatch.setattr(harness_mod, "resolve_provider", lambda *a, **k: provider)
    monkeypatch.chdir(ws)
    rec = asyncio.run(_harness(tmp_path, ws, provider).run("push the branch"))
    assert rec.status == "WAITING_INPUT", f"no pause; ran {runs.calls}"
    rc = cli_mod.main(["allow", rec.id, "--db", str(tmp_path / "t.db"), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out.strip().splitlines()[-1])["status"] == "COMPLETED"
    assert _allow(ws) == {"allow": ["git push"]}
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]


async def test_bash_tool_without_callback_refuses(ws: Path, runs: _Runs) -> None:
    policy = SandboxPolicy(workspace_root=ws)
    with pytest.raises(SandboxViolationError, match=r"\[APPROVAL NEEDED\]"):
        await make_bash_tool(policy).invoke([PUSH], stdin=None)
    seen: list[Any] = []
    try:
        tool = make_bash_tool(policy, on_approval=seen.append)  # type: ignore[call-arg]
    except TypeError as exc:
        pytest.fail(f"make_bash_tool has no on_approval callback: {exc}")
    out = await tool.invoke([PUSH], stdin=None)
    assert out.startswith("[APPROVAL NEEDED]")
    assert [(e.command, e.prefix) for e in seen] == [(PUSH, "git push")]
    assert runs.calls == []


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


# Plan risk: in a worktree session the approval must land in the project, not the worktree.
@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
async def test_worktree_approval_writes_project_allow_file(
    tmp_path: Path, runs: _Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "--allow-empty",
         "-m", "init")  # fmt: skip
    monkeypatch.chdir(repo)
    provider = FakeScriptedProvider([_bash(PUSH), _done("pushed")])
    h = Harness(provider=provider, db_path=tmp_path / "t.db", tools=["bash"], worktree=True)
    rec = await h.run("push the branch")
    assert rec.status == "WAITING_INPUT", f"no pause; ran {runs.calls}"
    worktree = rec.sandbox_config["worktree"]
    resumed = await h.send(rec.id, "approve")
    assert resumed.status == "COMPLETED"
    assert _allow(repo.resolve()) == {"allow": ["git push"]}
    assert not (Path(worktree) / ".tether" / "allow.json").exists()
    assert runs.outside()[0]["cwd"] == worktree


# DoD-2 through the CLI: `tether send <id> approve`.
def test_cli_send_approve_end_to_end(
    tmp_path: Path,
    ws: Path,
    runs: _Runs,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FakeScriptedProvider([_bash(PUSH), _done("pushed")])
    monkeypatch.setattr(harness_mod, "resolve_provider", lambda *a, **k: provider)
    monkeypatch.chdir(ws)
    rec = asyncio.run(_harness(tmp_path, ws, provider).run("push the branch"))
    assert rec.status == "WAITING_INPUT", f"no pause; ran {runs.calls}"
    rc = cli_mod.main(["send", rec.id, "--db", str(tmp_path / "t.db"), "--json", "approve"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out.strip().splitlines()[-1])["status"] == "COMPLETED"
    assert _allow(ws) == {"allow": ["git push"]}
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]


# DoD-2 through MCP: `tether_send` with `approve` (wait=True so it resumes inline, no worker).
async def test_mcp_send_approve_end_to_end(
    tmp_path: Path, ws: Path, runs: _Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, provider, rec = await _paused(tmp_path, ws, runs, _done("pushed"))
    monkeypatch.setattr(harness_mod, "resolve_provider", lambda *a, **k: provider)
    mcp = TetherMCP(db_path=tmp_path / "t.db", workspace=ws)
    out = await mcp.call("tether_send", {"id": rec.id, "message": "approve", "wait": True})
    assert out["status"] == "COMPLETED"
    assert "approval" not in out
    assert _allow(ws) == {"allow": ["git push"]}
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]


# The plan's `strip().lower()`: case and surrounding whitespace do not matter.
async def test_approve_is_case_and_whitespace_insensitive(
    tmp_path: Path, ws: Path, runs: _Runs
) -> None:
    h, _, rec = await _paused(tmp_path, ws, runs, _done("pushed"))
    resumed = await h.send(rec.id, " Approve\n")
    assert _allow(ws) == {"allow": ["git push"]}
    assert [c["argv"] for c in runs.outside()] == [["git", "push", "origin", "main"]]
    assert resumed.status == "COMPLETED"


# Messages queued behind the decision are not lost: they reach the model as follow-ups.
async def test_queued_messages_become_followups(tmp_path: Path, ws: Path, runs: _Runs) -> None:
    provider = FakeScriptedProvider([_bash(PUSH), _done("pushed and tagged")])
    h = _harness(tmp_path, ws, provider, worker_spawner=lambda sid: None)
    rec = await h.run("push the branch")
    assert rec.status == "WAITING_INPUT", f"no pause; ran {runs.calls}"
    await h.send(rec.id, "approve", headless=True)  # no-op worker: nothing resumes yet
    h.store.enqueue_inbox(rec.id, "also tag it v1.2")
    resumed = await h.execute_session(rec.id)
    prompt = _last_prompt(provider)
    assert "pushed-ok" in prompt
    assert "also tag it v1.2" in prompt
    assert _allow(ws) == {"allow": ["git push"]}
    assert resumed.status == "COMPLETED" and resumed.result == "pushed and tagged"
