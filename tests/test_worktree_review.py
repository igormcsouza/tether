"""`--worktree` review fixes (acceptance tests written by the reviewer's lead)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.cli import _async_main
from tether.worktree import WorktreeError, create_worktree

ROOT = Path(__file__).resolve().parents[1]


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout


def _bash(cmd: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd="bash", stdin=cmd))


def _done(text: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd="done", stdin=text))


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    _git(
        path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
    )
    monkeypatch.chdir(path)
    return path


def _harness(tmp_path: Path, responses: list[ModelResponse]) -> Harness:
    return Harness(
        provider=FakeScriptedProvider(responses),
        db_path=tmp_path / "t.db",
        tools=["bash"],
        worktree=True,
    )


async def test_text_status_prints_the_branch_line(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = await _harness(tmp_path, [_bash("echo hi > a.txt"), _done("ok")]).run("g")
    capsys.readouterr()
    assert await _async_main(["status", rec.id, "--db", str(tmp_path / "t.db")]) == 0
    out = capsys.readouterr().out
    assert f"branch tether/{rec.id} (" in out


async def test_a_failing_commit_keeps_a_terminal_status(repo: Path, tmp_path: Path) -> None:
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    rec = await _harness(tmp_path, [_bash("echo hi > a.txt"), _done("ok")]).run("g")
    assert rec.status in ("COMPLETED", "FAILED")
    assert rec.sandbox_config.get("commit") is None
    assert "commit" in (rec.result or "").lower()


async def test_resume_without_changes_sets_commit_null(repo: Path, tmp_path: Path) -> None:
    h = _harness(tmp_path, [_bash("echo hi > a.txt"), _done("ok"), _done("nothing new")])
    rec = await h.run("g")
    assert rec.sandbox_config["commit"]
    await h.send(rec.id, "check again")
    again = h.store.get_session(rec.id)
    assert again is not None and again.sandbox_config.get("commit") is None


def test_ref_starting_with_dash_is_refused(repo: Path) -> None:
    with pytest.raises(WorktreeError, match="ref"):
        create_worktree(repo, "ses_x", "--upload-pack=evil")


async def test_worktree_flags_need_worktree(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "t.db")
    assert await _async_main(["run", "--db", db, "--setup", "true", "g"]) == 1
    assert "--worktree" in capsys.readouterr().err
    assert await _async_main(["run", "--db", db, "--worktree-from", "main", "g"]) == 1
    assert "--worktree" in capsys.readouterr().err


def test_docs_say_keys_are_top_level() -> None:
    for page in ("docs/guides/own-branch.md", "docs/reference/agent-interface.md"):
        text = (ROOT / page).read_text()
        assert "sandbox_config" not in text, page
    assert "--worktree" in (ROOT / "README.md").read_text()
