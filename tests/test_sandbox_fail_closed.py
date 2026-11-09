"""Write sessions fail closed without bwrap unless the caller opts out (#124 item 2)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import tether.sandbox as sb_mod
from tests.conftest import FakeScriptedProvider
from tether import Harness, SandboxPolicy
from tether.cli import _async_main
from tether.store import SQLiteStore

NOTICE = "[sandbox] bwrap not available, running with command checks only"
MODE_TEXT = "command checks only"
_HINTS = ("--allow-unsandboxed", "TETHER_SANDBOX=container", "bubblewrap")
_PIPE_YAML = "name: fc\nstages:\n  - id: s1\n    model: fc-cli/m\n    goal: '{{goal}}'\n"


def _policy(tmp_path: Path, **kw: Any) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=tmp_path, **kw)


def _assert_actionable(msg: str) -> None:
    for hint in _HINTS:
        assert hint in msg, f"refusal lacks {hint!r}: {msg}"


def _no_rows(db: Path) -> None:
    assert SQLiteStore(db_path=db).list_sessions(limit=50) == []


@pytest.fixture
def no_bwrap(monkeypatch: pytest.MonkeyPatch) -> FakeScriptedProvider:
    """A host without bwrap. The fake answers `done` and is the provider for CLI and MCP too."""
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    monkeypatch.setattr(sb_mod, "_UNSANDBOXED_NOTICE_SHOWN", False)
    provider = FakeScriptedProvider([])
    monkeypatch.setattr("tether.harness.resolve_provider", lambda *a, **k: provider)
    return provider


def test_refused_without_bwrap(tmp_path: Path, no_bwrap: FakeScriptedProvider) -> None:
    """DoD-1 (Harness): refused before any model call and before any session row."""
    db = tmp_path / "t.db"
    harness = Harness(db_path=db, sandbox=_policy(tmp_path), provider=no_bwrap)
    with pytest.raises(sb_mod.SandboxUnavailableError) as info:
        asyncio.run(harness.run("g"))
    _assert_actionable(str(info.value))
    assert no_bwrap.recorded_calls == []
    _no_rows(db)


def test_refused_without_bwrap_cli_run(
    tmp_path: Path,
    no_bwrap: FakeScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD-1 (CLI run): exit 1 (usage) and the message names every way out."""
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    assert asyncio.run(_async_main(["run", "--db", str(db), "goal"])) == 1
    _assert_actionable(capsys.readouterr().err)
    assert no_bwrap.recorded_calls == []
    _no_rows(db)


def test_refused_without_bwrap_cli_pipeline(
    tmp_path: Path,
    no_bwrap: FakeScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD-1 (CLI pipeline): exit 1 before the first stage runs."""
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    manifest = tmp_path / "pipe.yaml"
    manifest.write_text(_PIPE_YAML, encoding="utf-8")
    rc = asyncio.run(_async_main(["pipeline", str(manifest), "--db", str(db), "Run it"]))
    assert rc == 1
    _assert_actionable(capsys.readouterr().err)
    assert no_bwrap.recorded_calls == []


def test_refused_without_bwrap_mcp(tmp_path: Path, no_bwrap: FakeScriptedProvider) -> None:
    """DoD-1 (MCP tether_run): ToolError with the same actionable message."""
    pytest.importorskip("mcp")
    from tether.mcp import TetherMCP, ToolError

    impl = TetherMCP(db_path=tmp_path / "t.db", workspace=tmp_path)
    with pytest.raises(ToolError) as info:
        asyncio.run(impl.call("tether_run", {"goal": "g"}))
    _assert_actionable(str(info.value))
    assert no_bwrap.recorded_calls == []


def test_refused_without_bwrap_spawn(
    tmp_path: Path, no_bwrap: FakeScriptedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-1 (spawn): no detached worker is launched for a refused session."""

    def _no_worker(*_a: Any, **_k: Any) -> None:
        raise AssertionError("worker spawned before the refusal")

    monkeypatch.setattr("tether.harness.subprocess.Popen", _no_worker)
    harness = Harness(db_path=tmp_path / "t.db", sandbox=_policy(tmp_path), provider=no_bwrap)
    with pytest.raises(sb_mod.SandboxUnavailableError):
        harness.spawn("g")


def test_opt_out_runs_with_notice_once(
    tmp_path: Path,
    no_bwrap: FakeScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD-2: every opt-out front door runs; the notice prints once per process."""
    pytest.importorskip("mcp")
    from tether.mcp import TetherMCP

    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    for _ in range(2):
        opted = Harness(
            db_path=db,
            sandbox=_policy(tmp_path, allow_unsandboxed=True),
            provider=FakeScriptedProvider([]),
        )
        assert asyncio.run(opted.run("g")).status == "COMPLETED"
    rc = asyncio.run(_async_main(["run", "--allow-unsandboxed", "--db", str(db), "goal"]))
    assert rc == 0
    impl = TetherMCP(db_path=db, workspace=tmp_path)
    out = asyncio.run(impl.call("tether_run", {"goal": "g", "allow_unsandboxed": True}))
    assert out["status"] == "COMPLETED"
    assert capsys.readouterr().err.count(NOTICE) == 1


@pytest.mark.parametrize("case", ["read-only", "no-kernel", "container"])
def test_unaffected_cases(
    case: str,
    tmp_path: Path,
    no_bwrap: FakeScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD-3: read-only, explicit kernel-off and TETHER_SANDBOX=container are not refused."""
    if case == "container":
        monkeypatch.setenv("TETHER_SANDBOX", "container")
    policies = {
        "read-only": _policy(tmp_path, profile="read-only"),
        "no-kernel": _policy(tmp_path, use_kernel_sandbox=False),
        "container": _policy(tmp_path),
    }
    harness = Harness(
        db_path=tmp_path / "t.db", sandbox=policies[case], provider=FakeScriptedProvider([])
    )
    rec = asyncio.run(harness.run("g"))
    assert rec.status == "COMPLETED"
    assert rec.sandbox_config["sandbox_mode"] == MODE_TEXT
    err = capsys.readouterr().err
    assert NOTICE not in err and "Sandbox unavailable" not in err


def test_bad_tether_sandbox_value(
    tmp_path: Path, no_bwrap: FakeScriptedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-3: a TETHER_SANDBOX value other than `container` is refused, naming the valid one."""
    monkeypatch.setenv("TETHER_SANDBOX", "docker")
    harness = Harness(db_path=tmp_path / "t.db", sandbox=_policy(tmp_path), provider=no_bwrap)
    with pytest.raises(sb_mod.SandboxUnavailableError, match="container"):
        asyncio.run(harness.run("g"))
    assert no_bwrap.recorded_calls == []


@pytest.mark.parametrize(
    ("usable", "opt_out", "expected"),
    [(False, True, "sandbox: command checks only"), (True, False, "sandbox: bwrap")],
)
def test_status_shows_sandbox_mode(
    tmp_path: Path,
    no_bwrap: FakeScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    usable: bool,
    opt_out: bool,
    expected: str,
) -> None:
    """DoD-4: `tether status` names the sandbox the session was created with."""
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: usable)
    db = tmp_path / "t.db"
    harness = Harness(
        db_path=db, sandbox=_policy(tmp_path, allow_unsandboxed=opt_out), provider=no_bwrap
    )
    rec = harness.create_session("g")
    assert asyncio.run(_async_main(["status", rec.id, "--db", str(db)])) == 0
    assert expected in capsys.readouterr().out


def test_status_old_row_has_no_sandbox_line(
    tmp_path: Path,
    no_bwrap: FakeScriptedProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD-4: rows stored before 0.3 carry no sandbox_mode and print no sandbox line."""
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: True)
    db = tmp_path / "t.db"
    harness = Harness(db_path=db, sandbox=_policy(tmp_path), provider=no_bwrap)
    rec = harness.create_session("g")
    assert rec.sandbox_config["sandbox_mode"] == "bwrap"
    cfg = dict(rec.sandbox_config)
    cfg.pop("sandbox_mode")
    harness.store.set_sandbox_config(rec.id, cfg)
    assert asyncio.run(_async_main(["status", rec.id, "--db", str(db)])) == 0
    assert "sandbox:" not in capsys.readouterr().out


def test_children_inherit_but_not_widen(
    tmp_path: Path, no_bwrap: FakeScriptedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-5: children inherit the opt-out, can only narrow it, and are re-checked at execute."""
    opted = _policy(tmp_path, allow_unsandboxed=True)
    closed = _policy(tmp_path)
    assert opted.attenuate().allow_unsandboxed is True
    assert opted.attenuate(child_allow_unsandboxed=False).allow_unsandboxed is False
    assert closed.attenuate(child_allow_unsandboxed=True).allow_unsandboxed is False
    assert SandboxPolicy.from_dict(opted.to_dict()).allow_unsandboxed is True
    assert SandboxPolicy.from_dict(closed.to_dict()).allow_unsandboxed is False

    stage_model = FakeScriptedProvider([])
    monkeypatch.setattr("tether.harness.resolve_provider", lambda *a, **k: stage_model)
    pipe = {
        "name": "fc",
        "stages": [{"id": "s1", "model": "fc-child/m", "tools": ["edit"], "goal": "do it"}],
    }
    harness = Harness(db_path=tmp_path / "t.db", sandbox=opted, provider=FakeScriptedProvider([]))
    root = asyncio.run(harness.run_pipeline(pipe, "Audit"))
    assert root.status == "COMPLETED"
    (child,) = harness.store.list_sessions(parent_id=root.id)
    assert child.sandbox_config["allow_unsandboxed"] is True
    assert child.status == "COMPLETED"

    pending = harness.create_session("again", parent_id=root.id)
    before = len(stage_model.recorded_calls)
    cfg = dict(pending.sandbox_config)
    cfg["allow_unsandboxed"] = False
    harness.store.set_sandbox_config(pending.id, cfg)
    refused = asyncio.run(harness.execute_session(pending.id))
    assert refused.status == "FAILED"
    assert "--allow-unsandboxed" in (refused.result or "")
    assert len(stage_model.recorded_calls) == before


def test_stored_session_refused_at_execute(tmp_path: Path, no_bwrap: FakeScriptedProvider) -> None:
    """Defence: a stored row without the opt-out fails at execute with no provider call."""
    db = tmp_path / "t.db"
    store = SQLiteStore(db_path=db)
    rec = store.create_session(
        goal="g",
        model="fake/x",
        skill=None,
        tools=[],
        sandbox_config=_policy(tmp_path).to_dict(),
        parent_id=None,
        max_steps=5,
        session_id=None,
        max_tokens=None,
        token_grant=None,
    )
    done = asyncio.run(Harness(db_path=db, provider=no_bwrap).execute_session(rec.id))
    assert done.status == "FAILED"
    _assert_actionable(done.result or "")
    assert no_bwrap.recorded_calls == []


def test_pipeline_narrowed_to_read_only_is_not_refused(
    tmp_path: Path, no_bwrap: FakeScriptedProvider
) -> None:
    """Bad day: a stage narrowing the root to read-only is not refused without bwrap."""
    pipe = {
        "name": "ro",
        "stages": [
            {
                "id": "audit",
                "model": "fc-ro/m",
                "sandbox": "read-only",
                "tools": ["edit"],
                "goal": "audit",
            }
        ],
    }
    harness = Harness(db_path=tmp_path / "t.db", sandbox=_policy(tmp_path), provider=no_bwrap)
    root = asyncio.run(harness.run_pipeline(pipe, "Audit only"))
    assert root.status == "COMPLETED"
    assert root.sandbox_config["sandbox_mode"] == MODE_TEXT


def test_worktree_refused_before_worktree_exists(
    tmp_path: Path, no_bwrap: FakeScriptedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad day: a --worktree write session is refused before the worktree is created."""

    def _no_worktree(*_a: Any, **_k: Any) -> None:
        raise AssertionError("worktree created before the refusal")

    monkeypatch.setattr("tether.harness.repo_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr("tether.harness.create_worktree", _no_worktree)
    harness = Harness(
        db_path=tmp_path / "t.db",
        sandbox=_policy(tmp_path),
        worktree=True,
        provider=no_bwrap,
    )
    with pytest.raises(sb_mod.SandboxUnavailableError):
        harness.create_session("g")


def test_bwrap_present_no_refusal_no_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bad day: with bwrap present a write session runs with mode bwrap and no notice."""
    monkeypatch.delenv("TETHER_SANDBOX", raising=False)
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: True)
    monkeypatch.setattr(sb_mod, "_UNSANDBOXED_NOTICE_SHOWN", False)
    harness = Harness(
        db_path=tmp_path / "t.db", sandbox=_policy(tmp_path), provider=FakeScriptedProvider([])
    )
    rec = asyncio.run(harness.run("g"))
    assert rec.status == "COMPLETED"
    assert rec.sandbox_config["sandbox_mode"] == "bwrap"
    assert NOTICE not in capsys.readouterr().err


def test_harness_kwarg_opt_out_does_not_mutate_policy(
    tmp_path: Path, no_bwrap: FakeScriptedProvider
) -> None:
    """DoD-2 (SDK Harness kwarg): runs, and the caller's policy object is untouched."""
    policy = _policy(tmp_path)
    harness = Harness(
        db_path=tmp_path / "t.db", sandbox=policy, provider=no_bwrap, allow_unsandboxed=True
    )
    assert asyncio.run(harness.run("g")).status == "COMPLETED"
    assert policy.allow_unsandboxed is False


def test_cli_pipeline_opt_out_runs(
    tmp_path: Path, no_bwrap: FakeScriptedProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-2 (CLI pipeline): --allow-unsandboxed exists on the pipeline parser and runs."""
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "pipe.yaml"
    manifest.write_text(_PIPE_YAML, encoding="utf-8")
    argv = ["pipeline", str(manifest), "--allow-unsandboxed", "--db", str(tmp_path / "t.db"), "go"]
    assert asyncio.run(_async_main(argv)) == 0


def test_bad_tether_sandbox_refused_with_bwrap_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 2: a bad TETHER_SANDBOX is refused on every host, even when bwrap is present."""
    monkeypatch.setenv("TETHER_SANDBOX", "docker")
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: True)
    provider = FakeScriptedProvider([])
    harness = Harness(db_path=tmp_path / "t.db", sandbox=_policy(tmp_path), provider=provider)
    with pytest.raises(sb_mod.SandboxUnavailableError, match="container"):
        asyncio.run(harness.run("g"))
    assert provider.recorded_calls == []


def test_stored_session_bad_env_fails_session_at_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 1: a bad TETHER_SANDBOX in the worker env fails the session, it does not raise."""
    db = tmp_path / "t.db"
    store = SQLiteStore(db_path=db)
    rec = store.create_session(
        goal="g",
        model="fake/x",
        skill=None,
        tools=[],
        sandbox_config=_policy(tmp_path).to_dict(),
        parent_id=None,
        max_steps=5,
        session_id=None,
        max_tokens=None,
        token_grant=None,
    )
    monkeypatch.setenv("TETHER_SANDBOX", "docker")
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: True)
    provider = FakeScriptedProvider([])
    done = asyncio.run(Harness(db_path=db, provider=provider).execute_session(rec.id))
    assert done.status == "FAILED"
    assert "container" in (done.result or "")
    assert provider.recorded_calls == []
