"""Headless workers must import the installed tether, never a workspace's own package (#273)."""

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
