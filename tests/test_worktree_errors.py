import subprocess
from pathlib import Path

import pytest

from tether import worktree
from tether.worktree import WorktreeError, commit_all, create_worktree


def test_create_worktree_wraps_mkdir_oserror(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".cache").write_text("not a directory")
    with pytest.raises(WorktreeError, match="cannot create worktree directory"):
        create_worktree(tmp_path / "repo", "abc123", None)


def test_commit_all_raises_on_diff_error(tmp_path, monkeypatch):
    def fake_git(path, *args):
        code = 128 if args[:2] == ("diff", "--cached") else 0
        return subprocess.CompletedProcess(args, code, stdout="", stderr="fatal: boom\n")

    monkeypatch.setattr(worktree, "_git", fake_git)
    with pytest.raises(WorktreeError, match="git diff failed: fatal: boom"):
        commit_all(tmp_path, "abc", "goal")
