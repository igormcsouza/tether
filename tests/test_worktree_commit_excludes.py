from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tether.worktree import commit_all


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "tracked.txt").write_text("v1\n")
    _git(root, "add", "tracked.txt")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    return root


def _write(root: Path, rel: str, text: str = "x\n") -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _committed(root: Path) -> set[str]:
    return set(_git(root, "show", "--name-only", "--format=", "HEAD").splitlines())


def test_pyc_not_committed(repo: Path) -> None:
    _write(repo, "calc.py", "print(1)\n")
    _write(repo, "__pycache__/calc.cpython-312.pyc", "bytecode")
    assert commit_all(repo, "s1", "add calc") is not None
    assert _committed(repo) == {"calc.py"}


@pytest.mark.parametrize(
    "rel",
    [
        "__pycache__/calc.cpython-312.pyc",
        "pkg/__pycache__/m.pyc",
        "loose.pyc",
        "a/b/c/deep.pyc",
        ".pytest_cache/v/cache/nodeids",
        ".ruff_cache/CACHEDIR.TAG",
        "pkg/.mypy_cache/3.12/x.json",
        ".tether/s1/log.jsonl",
        "sub/.tether/x",
    ],
)
def test_cache_dirs_not_committed(repo: Path, rel: str) -> None:
    _write(repo, "calc.py")
    _write(repo, rel)
    assert commit_all(repo, "s1", "g") is not None
    assert _committed(repo) == {"calc.py"}


def test_real_changes_still_committed(repo: Path) -> None:
    _write(repo, "calc.py")
    _write(repo, "sub/mod.py")
    (repo / "tracked.txt").write_text("v2\n")
    _write(repo, "__pycache__/calc.cpython-312.pyc")
    assert commit_all(repo, "s1", "g") is not None
    assert _committed(repo) == {"calc.py", "sub/mod.py", "tracked.txt"}


def test_gitignore_respected(repo: Path) -> None:
    _write(repo, ".gitignore", "build/\n")
    _write(repo, "build/out.txt")
    _write(repo, "calc.py")
    assert commit_all(repo, "s1", "g") is not None
    assert _committed(repo) == {".gitignore", "calc.py"}


def test_only_excluded_means_no_commit(repo: Path) -> None:
    _write(repo, "__pycache__/calc.cpython-312.pyc")
    _write(repo, "x.pyc")
    before = _git(repo, "rev-parse", "HEAD")
    assert commit_all(repo, "s1", "g") is None
    assert _git(repo, "rev-parse", "HEAD") == before


def test_pyc_suffix_is_exact(repo: Path) -> None:
    _write(repo, "notes.pyc.txt")
    assert commit_all(repo, "s1", "g") is not None
    assert _committed(repo) == {"notes.pyc.txt"}


def test_second_call_without_changes_is_none(repo: Path) -> None:
    _write(repo, "calc.py")
    assert commit_all(repo, "s1", "g") is not None
    assert commit_all(repo, "s1", "g") is None
