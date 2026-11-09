# `tether diff` sees writes by sed -i, perl -i, mv, cp and python (#280).
from __future__ import annotations

import os
import shlex
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, SQLiteStore
from tether.cli import _async_main
from tether.diff import SCAN_LIMIT
from tether.sandbox import SandboxPolicy


def _step(cmd: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd=cmd))


def _py(code: str) -> str:
    # a python one-liner, quoted so the shell passes `code` on as one argument
    return "python3 -c " + shlex.quote(code)


async def _run(root: Path, db: Path, cmds: list[str]) -> str:
    sandbox = SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)
    provider = FakeScriptedProvider([_step(cmd) for cmd in cmds])
    h = Harness(db_path=db, tools=["bash"], provider=provider, sandbox=sandbox)
    return (await h.run("goal")).id


def _pre_date(*paths: Path) -> None:
    # untouched since the session started: the bytes the session sees first are these
    past = time.time() - 3600
    for path in paths:
        os.utime(path, (past, past))


async def _diff(capsys: pytest.CaptureFixture[str], sid: str, db: Path) -> str:
    code = await _async_main(["diff", sid, "--db", str(db)])
    out, _ = capsys.readouterr()
    assert code == 0, out
    return out


def _snapshot_paths(db: Path, sid: str) -> list[str]:
    return [rel for rel, _ in SQLiteStore(db_path=db).list_snapshots(sid)]


async def test_sed_i_is_diffed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, ["sed -i 's/a/b/' f"])
    out = await _diff(capsys, sid, db)
    assert "-a\n" in out and "+b\n" in out
    assert "no file changes" not in out


@pytest.mark.parametrize(
    "tool",
    [
        pytest.param(
            "perl", marks=pytest.mark.skipif(shutil.which("perl") is None, reason="no perl")
        ),
        "mv",
        "cp",
    ],
)
async def test_perl_mv_cp_are_diffed(
    tool: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cmds = {
        "perl": "perl -i -pe 's/old/new/' f",
        "mv": "mv new f",
        "cp": "cp new f",
    }
    f, new = tmp_path / "f", tmp_path / "new"
    f.write_text("old\n")
    new.write_text("new\n")
    _pre_date(f, new)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, [cmds[tool]])
    out = await _diff(capsys, sid, db)
    assert "a/f" in out and "-old\n" in out and "+new\n" in out


async def test_python_write_never_reported_as_no_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "f"
    f.write_text("old\n")
    _pre_date(f)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, [_py("open('f', 'w').write('x')")])
    out = await _diff(capsys, sid, db)
    assert "+x" in out
    assert "no file changes" not in out


async def test_untracked_writer_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "w.py"
    script.write_text("open('out.txt', 'w').write('1')\n")
    _pre_date(script)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, ["python3 w.py"])
    out = await _diff(capsys, sid, db)
    assert "out.txt" in out and "could not track" in out
    assert "no file changes" not in out


async def test_read_only_commands_snapshot_nothing(tmp_path: Path) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, ["cat f", "grep a f", "ls"])
    assert SQLiteStore(db_path=db).list_snapshots(sid) == []


async def test_large_workspace_is_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    for d in range(25):
        sub = tmp_path / f"d{d:02d}"
        sub.mkdir()
        for i in range(100):
            (sub / f"x{i}.txt").write_text("")
    db = tmp_path / "t.db"
    real_walk = os.walk

    def no_walk(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a command must not walk the workspace")

    monkeypatch.setattr(os, "walk", no_walk)
    sid = await _run(tmp_path, db, ["sed -i 's/a/b/' f"])
    assert _snapshot_paths(db, sid) == ["f"]

    seen: list[int] = []

    def counting_walk(
        top: str, *args: Any, **kwargs: Any
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        for entry in real_walk(top, *args, **kwargs):
            seen.append(len(entry[2]))
            yield entry

    monkeypatch.setattr(os, "walk", counting_walk)
    out = await _diff(capsys, sid, db)
    assert "+b\n" in out and "more than 2000 files" in out
    assert sum(seen) <= SCAN_LIMIT + 100  # the walk stopped at the ceiling, not after every file


async def test_unterminated_quote_does_not_hide_later_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, ["sed -i 's/a f", "sed -i 's/a/b/' f"])
    out = await _diff(capsys, sid, db)
    assert "+b\n" in out


async def test_arg_outside_root_or_dir_not_snapshotted(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "sub").mkdir(parents=True)
    f = root / "f"
    f.write_text("a\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("a\n")
    _pre_date(f, outside)
    db = tmp_path / "t.db"
    sid = await _run(root, db, ["sed -i 's/a/b/' f sub ../outside.txt"])
    assert _snapshot_paths(db, sid) == ["f"]


async def test_file_changed_after_the_session_is_not_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, [_py("open('in.txt', 'w').write('1')")])
    late = tmp_path / "late.txt"
    late.write_text("1")
    future = time.time() + 3600
    os.utime(late, (future, future))
    out = await _diff(capsys, sid, db)
    assert "in.txt" in out and "late.txt" not in out


async def test_db_hidden_and_pycache_not_listed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    code = (
        "import os; os.makedirs('.hidden', exist_ok=True); "
        "os.makedirs('__pycache__', exist_ok=True); "
        "open('.hidden/x', 'w').write('1'); "
        "open('__pycache__/x.pyc', 'w').write('1'); "
        "open('visible.txt', 'w').write('2')"
    )
    sid = await _run(tmp_path, db, [_py(code)])
    out = await _diff(capsys, sid, db)
    assert "visible.txt" in out
    assert ".hidden" not in out and "__pycache__" not in out and "t.db" not in out


async def test_more_than_20_untracked_paths_are_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    code = "for i in range(25): open('u%02d.txt' % i, 'w').write('x')"
    sid = await _run(tmp_path, db, [_py(code)])
    out = await _diff(capsys, sid, db)
    assert "could not track" in out and "+5 more" in out


async def test_identical_snapshot_does_not_hide_untracked_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, ["sed -i 's/zzz/y/' f", _py("open('g.txt', 'w').write('1')")])
    out = await _diff(capsys, sid, db)
    assert "g.txt" in out and "could not track" in out
    assert "no file changes remain" not in out


async def test_absolute_path_is_keyed_relative_to_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, [f"sed -i 's/a/b/' {f}"])
    assert _snapshot_paths(db, sid) == ["f"]
    out = await _diff(capsys, sid, db)
    assert "a/f" in out and "+b\n" in out
    assert "could not track" not in out and str(tmp_path) not in out


async def test_bailed_walk_with_no_diff_prints_neither_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "f"
    f.write_text("a\n")
    _pre_date(f)
    for d in range(25):
        sub = tmp_path / f"d{d:02d}"
        sub.mkdir()
        for i in range(100):
            (sub / f"x{i}.txt").write_text("")
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, ["sed -i 's/zzz/y/' f"])
    out = await _diff(capsys, sid, db)
    assert "more than 2000 files" in out
    assert "no file changes recorded" not in out
    assert "no file changes remain" not in out


async def test_pre_dated_untracked_file_is_not_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = tmp_path / "old.txt"
    old.write_text("x")
    _pre_date(old)
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, [_py("open('in.txt', 'w').write('1')")])
    out = await _diff(capsys, sid, db)
    assert "in.txt" in out and "old.txt" not in out


async def test_stat_prints_untracked_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    sid = await _run(tmp_path, db, [_py("open('u.txt', 'w').write('1')")])
    code = await _async_main(["diff", sid, "--db", str(db), "--stat"])
    out, _ = capsys.readouterr()
    assert code == 0
    assert out.splitlines()[-1].startswith("1 file changed by commands tether could not track")
