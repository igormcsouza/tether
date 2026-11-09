"""QA fixes on the escalation: a refused approval saves nothing, the approved stdin reaches the
command, and a failed allow-file write leaves no temp file behind. Fakes only, no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import tether.sandbox as sb_mod
from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, SandboxPolicy, SandboxViolationError
from tether.sandbox import add_to_allow_file

PUSH = "git push origin main"


class _Proc:
    def __init__(self, rec: dict[str, Any]) -> None:
        self.pid = 4242
        self.returncode = 0
        self._rec = rec

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        self._rec["stdin"] = input
        return b"pushed-ok\n", b""

    async def wait(self) -> int:
        return self.returncode


@pytest.fixture
def execs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_exec(*argv: str, **kwargs: Any) -> _Proc:
        rec: dict[str, Any] = {"argv": list(argv), "stdin": None}
        calls.append(rec)
        return _Proc(rec)

    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    monkeypatch.setattr(sb_mod.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(sb_mod.os, "killpg", lambda pid, sig: None)
    return calls


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path.resolve()


def _bash(cmd: str, stdin: str | None = None) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd=cmd, stdin=stdin))


def _done(text: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd="done", stdin=text))


def _harness(tmp_path: Path, ws: Path, provider: Any) -> Harness:
    return Harness(
        provider=provider,
        db_path=tmp_path / "t.db",
        tools=["bash"],
        sandbox=SandboxPolicy(workspace_root=ws),
    )


def _last_prompt(provider: FakeScriptedProvider) -> str:
    return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[-1])


async def test_refused_approval_saves_nothing(
    tmp_path: Path, ws: Path, execs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeScriptedProvider([_bash(f"bash {PUSH}"), _done("gave up")])
    h = _harness(tmp_path, ws, provider)
    rec = await h.run("push the branch")
    assert rec.status == "WAITING_INPUT"

    async def refuse(self: SandboxPolicy, cmd: str, stdin: str | None = None) -> str:
        raise SandboxViolationError("refused by the jail")

    monkeypatch.setattr(SandboxPolicy, "execute_bash", refuse)
    await h.send(rec.id, "approve")
    assert not (ws / ".tether" / "allow.json").exists()
    assert "approval failed, nothing ran" in _last_prompt(provider)


async def test_approved_command_gets_its_stdin(
    tmp_path: Path, ws: Path, execs: list[dict[str, Any]]
) -> None:
    provider = FakeScriptedProvider([_bash(f"bash {PUSH}", stdin="payload"), _done("pushed")])
    h = _harness(tmp_path, ws, provider)
    rec = await h.run("push the branch")
    assert rec.status == "WAITING_INPUT"
    assert rec.sandbox_config["approval"]["stdin"] == "payload"
    await h.send(rec.id, "approve")
    outside = [c for c in execs if c["argv"][0] != "bwrap"]
    assert outside and b"payload" in (outside[-1]["stdin"] or b"")


def test_failed_allow_write_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(src: Any, dst: Any) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(sb_mod.os, "replace", boom)
    with pytest.raises(OSError):
        add_to_allow_file(tmp_path, "git push")
    assert list((tmp_path / ".tether").glob("allow.json*")) == []


async def test_failed_allow_save_still_returns_output(
    tmp_path: Path, ws: Path, execs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import tether.harness as harness_mod

    provider = FakeScriptedProvider([_bash(f"bash {PUSH}"), _done("pushed")])
    h = _harness(tmp_path, ws, provider)
    rec = await h.run("push the branch")
    assert rec.status == "WAITING_INPUT"

    def boom(root: Path, prefix: str) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(harness_mod, "add_to_allow_file", boom)
    await h.send(rec.id, "approve")
    prompt = _last_prompt(provider)
    assert "pushed-ok" in prompt
    assert "ran, but the prefix could not be saved: read-only" in prompt
    assert not (ws / ".tether" / "allow.json").exists()
