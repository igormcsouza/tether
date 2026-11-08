"""Tests for `tether run --worktree`: git worktrees, setup, and commit at stop."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.api import worktree_line
from tether.cli import main
from tether.worktree import WorktreeError, commit_all, create_worktree, repo_root, run_setup


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout


def _bash(cmd: str) -> ModelResponse:
    return ModelResponse(content="step", action=ActionCall(cmd="bash", stdin=cmd))


def _done(text: str) -> ModelResponse:
    return ModelResponse(content="done", action=ActionCall(cmd="done", stdin=text))


def _harness(tmp_path: Path, provider: FakeScriptedProvider, **kw: object) -> Harness:
    kw.setdefault("tools", ["bash", "edit"])
    return Harness(provider=provider, db_path=tmp_path / "t.db", **kw)  # type: ignore[arg-type]


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
        "init",
    )
    monkeypatch.chdir(path)
    return path


async def test_worktree_run_commits_on_branch(repo: Path, tmp_path: Path) -> None:
    provider = FakeScriptedProvider([_bash("echo hi > out.txt"), _done("ok")])
    rec = await _harness(tmp_path, provider, worktree=True).run("write out")
    branch = f"tether/{rec.id}"
    assert rec.status == "COMPLETED"
    assert rec.sandbox_config["branch"] == branch
    assert _git(repo, "show", f"{branch}:out.txt") == "hi\n"
    assert _git(repo, "log", "-1", "--format=%s", branch).startswith(f"tether {rec.id}: ")
    assert rec.sandbox_config["commit"] == _git(repo, "rev-parse", branch).strip()


async def test_worktree_no_changes_no_commit(repo: Path, tmp_path: Path) -> None:
    provider = FakeScriptedProvider([_done("nothing to do")])
    rec = await _harness(tmp_path, provider, worktree=True).run("look only")
    check = subprocess.run(
        ["git", "rev-parse", "--verify", f"tether/{rec.id}"],
        cwd=repo,
        capture_output=True,
    )
    assert rec.sandbox_config["commit"] is None
    assert check.returncode == 0
    line = worktree_line(rec)
    assert line is not None and "no changes" in line


async def test_worktree_from_ref(repo: Path, tmp_path: Path) -> None:
    _git(repo, "branch", "base")
    base_sha = _git(repo, "rev-parse", "base").strip()
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "second",
    )
    provider = FakeScriptedProvider([_done("ok")])
    harness = _harness(tmp_path, provider, worktree=True, worktree_from="base")
    rec = await harness.run("from base")
    path = Path(str(rec.sandbox_config["worktree"]))
    assert _git(path, "rev-parse", "HEAD").strip() == base_sha


async def test_setup_failure_ends_failed_without_model(repo: Path, tmp_path: Path) -> None:
    provider = FakeScriptedProvider([])
    rec = await _harness(tmp_path, provider, worktree=True, setup="exit 3").run("never runs")
    assert rec.status == "FAILED"
    assert "setup failed (exit 3)" in (rec.result or "")
    assert len(provider.recorded_calls) == 0


async def test_resume_reuses_worktree(repo: Path, tmp_path: Path) -> None:
    provider = FakeScriptedProvider(
        [_bash("echo a > a.txt"), _done("first"), _bash("echo b > b.txt"), _done("second")]
    )
    harness = _harness(tmp_path, provider, worktree=True)
    rec = await harness.run("write a")
    path = rec.sandbox_config["worktree"]
    rec = await harness.send(rec.id, "now write b")
    assert rec.sandbox_config["worktree"] == path
    assert _git(repo, "rev-list", "--count", f"tether/{rec.id}").strip() == "3"


def test_not_a_repo_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    with pytest.raises(WorktreeError, match="needs a git repository"):
        repo_root(plain)
    assert main(["run", "--worktree", "x"]) == 1
    assert "needs a git repository" in capsys.readouterr().err


def test_create_worktree_bad_ref_is_usage_error(repo: Path) -> None:
    with pytest.raises(WorktreeError, match="git worktree add failed"):
        create_worktree(repo, "bad001", "no-such-ref")


def test_run_setup_ok_and_timeout(tmp_path: Path) -> None:
    assert run_setup(tmp_path, "true") is None
    msg = run_setup(tmp_path, "sleep 5", timeout=0.2)
    assert msg is not None and "timed out" in msg


async def test_worktree_line_none_without_worktree(repo: Path, tmp_path: Path) -> None:
    provider = FakeScriptedProvider([_done("ok")])
    rec = await _harness(tmp_path, provider).run("plain run")
    assert worktree_line(rec) is None


def test_headless_not_a_repo_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    assert main(["run", "--headless", "--worktree", "x"]) == 1
    assert "needs a git repository" in capsys.readouterr().err


async def test_mcp_worktree_outside_repo_is_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mcp = pytest.importorskip("mcp")

    from tether.mcp import build_server

    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    async with mcp.Client(build_server(tmp_path / "t.db", tmp_path)) as c:
        res = await c.call_tool("tether_run", {"goal": "g", "worktree": True})
    assert res.is_error
    assert "needs a git repository" in res.content[0].text


def test_git_missing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    with pytest.raises(WorktreeError, match="needs git on PATH"):
        repo_root(repo)


def test_commit_author(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    (repo / "f1.txt").write_text("1\n")
    sha = commit_all(repo, "aaa111", "first goal")
    assert sha is not None
    assert _git(repo, "log", "-1", "--format=%an <%ae>", sha).strip() == "tether <tether@localhost>"
    _git(repo, "config", "user.name", "Ann")
    _git(repo, "config", "user.email", "ann@example.com")
    (repo / "f2.txt").write_text("2\n")
    sha2 = commit_all(repo, "aaa111", "second goal")
    assert sha2 is not None
    assert _git(repo, "log", "-1", "--format=%an <%ae>", sha2).strip() == "Ann <ann@example.com>"
