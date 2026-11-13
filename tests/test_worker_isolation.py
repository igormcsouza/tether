"""Headless workers must import the installed tether, never a workspace's own package (#273)."""

import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tether import harness

REPO_TETHER = Path(__file__).resolve().parents[1] / "tether"
SHADOW = "raise RuntimeError('shadowed')\n"


def _spawn_argv(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> list[str]:
    seen: list[list[str]] = []

    def fake_popen(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        seen.append(list(argv))
        return SimpleNamespace(pid=1)

    with monkeypatch.context() as patch:
        patch.setattr(harness.subprocess, "Popen", fake_popen)
        harness.spawn_detached_worker(db_path, "sid")
    assert len(seen) == 1
    return seen[0]


def test_spawn_argv_has_dash_P(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    argv = _spawn_argv(monkeypatch, tmp_path / "db")
    assert "-P" in argv, f"worker argv lacks -P: {argv}"
    assert argv.index("-P") < argv.index("-m")
    assert argv[argv.index("-m") + 1] == "tether.cli"


@pytest.mark.parametrize("kind", ["package", "module"])
def test_workspace_tether_package_is_not_imported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    argv = _spawn_argv(monkeypatch, tmp_path / "db")
    ws = (tmp_path / "ws").resolve()
    ws.mkdir()
    if kind == "package":
        (ws / "tether").mkdir()
        (ws / "tether" / "__init__.py").write_text(SHADOW)
    else:
        (ws / "tether.py").write_text(SHADOW)
    head = argv[: argv.index("_worker")]
    result = subprocess.run([*head, "--help"], cwd=ws, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    probe = subprocess.run(
        [sys.executable, "-P", "-c", "import tether; print(tether.__file__)"],
        cwd=ws,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not Path(probe.stdout.strip()).resolve().is_relative_to(ws)


def test_no_other_unisolated_spawn() -> None:
    hits: list[str] = []
    for path in REPO_TETHER.rglob("*.py"):
        text = path.read_text()
        for match in re.finditer(r'"-m",\s*"tether', text):
            start = text.rfind("[", 0, match.start())
            assert start >= 0, f"{path}: spawn outside a list literal"
            segment = text[start : match.end()]
            hits.append(f"{path}: {segment!r}")
            assert '"-P"' in segment and segment.index('"-P"') < segment.index('"-m"'), (
                f"{path} spawns tether without -P: {segment!r}"
            )
    assert hits, "no spawn sites found; the scan is broken"


def _spawn_env(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> dict[str, str]:
    seen: list[dict[str, str]] = []

    def fake_popen(argv: list[str], **kwargs: object) -> SimpleNamespace:
        env = kwargs["env"]
        assert isinstance(env, dict)
        seen.append(dict(env))
        return SimpleNamespace(pid=1)

    with monkeypatch.context() as patch:
        patch.setattr(harness.subprocess, "Popen", fake_popen)
        harness.spawn_detached_worker(db_path, "sid")
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (".", None),
        ("", None),
        ("  ", None),
        ("~/x", None),
        (None, None),
        (":/abs/x", "/abs/x"),
        ("rel:/abs/x:", "/abs/x"),
        ("/a::/b", "/a:/b"),
        ("/a:/b", "/a:/b"),
        ("/a:/a", "/a:/a"),
    ],
)
def test_worker_pythonpath_keeps_only_absolute_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str | None, expected: str | None
) -> None:
    if raw is None:
        monkeypatch.delenv("PYTHONPATH", raising=False)
    else:
        monkeypatch.setenv("PYTHONPATH", raw)
    env = _spawn_env(monkeypatch, tmp_path / "db")
    if expected is None:
        assert "PYTHONPATH" not in env, f"PYTHONPATH kept: {env.get('PYTHONPATH')!r}"
    else:
        assert env["PYTHONPATH"] == expected


def test_spawn_does_not_mutate_caller_environ(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PYTHONPATH", "rel:/abs/x:")
    before = dict(os.environ)
    _spawn_env(monkeypatch, tmp_path / "db")
    assert dict(os.environ) == before


def test_worker_probe_imports_installed_tether_not_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ws = (tmp_path / "ws").resolve()
    (ws / "tether").mkdir(parents=True)
    (ws / "tether" / "__init__.py").write_text(SHADOW)
    monkeypatch.setenv("PYTHONPATH", ".")
    env = _spawn_env(monkeypatch, tmp_path / "db")
    probe = subprocess.run(
        [sys.executable, "-P", "-c", "import tether; print(tether.__file__)"],
        cwd=ws,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    assert not Path(probe.stdout.strip()).resolve().is_relative_to(ws)
