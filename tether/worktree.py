"""Git worktrees for `tether run --worktree`. Only harness code runs git; the model never does."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class WorktreeError(Exception):
    """A worktree could not be created. The message is user-facing."""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def repo_root(cwd: Path) -> Path:
    if shutil.which("git") is None:
        raise WorktreeError("--worktree needs git on PATH (install git, or drop --worktree)")
    out = _git(cwd, "rev-parse", "--show-toplevel")
    if out.returncode != 0:
        raise WorktreeError(
            "--worktree needs a git repository (run inside one, or drop --worktree)"
        )
    return Path(out.stdout.strip())


def create_worktree(repo: Path, session_id: str, ref: str | None) -> tuple[Path, str]:
    if ref is not None and ref.startswith("-"):
        raise WorktreeError(f"refusing ref {ref!r}: it must not start with '-'")
    branch = f"tether/{session_id}"
    path = Path.home() / ".cache" / "tether" / "worktrees" / f"{repo.name}-{session_id}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorktreeError(f"cannot create worktree directory {path.parent}: {exc}") from exc
    out = _git(repo, "worktree", "add", "-b", branch, str(path), ref or "HEAD")
    if out.returncode != 0:
        raise WorktreeError(f"git worktree add failed: {out.stderr.strip()}")
    return path, branch


def run_setup(path: Path, cmd: str, timeout: float = 300) -> str | None:
    """Run `sh -c cmd` in the worktree, outside the model sandbox. None means success."""
    try:
        done = subprocess.run(
            ["sh", "-c", cmd], cwd=path, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return f"setup timed out after {timeout:g} s. Fix --setup or drop it."
    if done.returncode == 0:
        return None
    tail = "\n".join((done.stdout + done.stderr).splitlines()[-20:])
    return f"setup failed (exit {done.returncode}): {tail}. Fix --setup or drop it."


def commit_all(path: Path, session_id: str, goal: str) -> str | None:
    """Stage everything and commit if anything changed. Returns the full sha, or None."""
    _git(path, "add", "-A")
    diff = _git(path, "diff", "--cached", "--quiet")
    if diff.returncode == 0:
        return None
    if diff.returncode != 1:
        raise WorktreeError(f"git diff failed: {diff.stderr.strip()}")
    subject = (goal.strip().splitlines() or [""])[0][:60]
    author: list[str] = []
    for key, default in (("user.name", "tether"), ("user.email", "tether@localhost")):
        if _git(path, "config", key).returncode != 0:
            author += ["-c", f"{key}={default}"]
    subprocess.run(
        ["git", *author, "commit", "-q", "-m", f"tether {session_id}: {subject}"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    return _git(path, "rev-parse", "HEAD").stdout.strip()
