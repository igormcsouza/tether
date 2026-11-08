from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, SQLiteStore
from tether.cli import _async_main
from tether.sandbox import SandboxPolicy
from tether.unchanged import missing_targets


def _step(cmd: str, stdin: str | None = None) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd=cmd, stdin=stdin))


async def _session(root: Path, db: Path, steps: list[ModelResponse] | None = None) -> str:
    sandbox = SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)
    h = Harness(db_path=db, provider=FakeScriptedProvider(steps or []), sandbox=sandbox)
    return (await h.run("goal")).id


async def _with_snapshots(root: Path, db: Path, snaps: list[tuple[str, bytes | None]]) -> str:
    sid = await _session(root, db)
    store = SQLiteStore(db_path=db)
    for path, content in snaps:
        store.record_snapshot(sid, path, content)
    return sid


async def _diff(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = await _async_main(["diff", *argv])
    out, err = capsys.readouterr()
    return code, out, err


async def test_snapshot_recorded_once_per_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    past = time.time() - 3600
    os.utime(tmp_path / "a.py", (past, past))  # untouched since the session started
    db = tmp_path / "t.db"
    steps = [_step("edit write a.py", "x=2\n"), _step("edit write a.py", "x=3\n")]
    sid = await _session(tmp_path, db, steps)
    assert SQLiteStore(db_path=db).list_snapshots(sid) == [("a.py", b"x=1\n")]


async def test_new_file_snapshot_is_null(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    sid = await _session(tmp_path, db, [_step("edit write new.txt", "hi\n")])
    assert SQLiteStore(db_path=db).list_snapshots(sid) == [("new.txt", None)]


async def test_diff_unified_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "t.db"
    (tmp_path / "a.py").write_text("x=2\n")
    sid = await _with_snapshots(tmp_path, db, [("a.py", b"x=1\n")])
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert out.startswith("--- a/a.py")
    assert "-x=1\n" in out and "+x=2\n" in out


async def test_diff_stat_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "t.db"
    (tmp_path / "a.py").write_text("x=2\n")
    sid = await _with_snapshots(tmp_path, db, [("a.py", b"x=1\n")])
    code, out, _ = await _diff(capsys, sid, "--stat", "--db", str(db))
    assert code == 0
    assert out == "a.py +1 -1\n"


async def test_diff_deleted_file_fully_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    sid = await _with_snapshots(tmp_path, db, [("a.py", b"a\nb\n")])
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert "-a\n-b\n" in out
    assert not [
        line for line in out.splitlines() if line.startswith("+") and not line.startswith("+++")
    ]


async def test_diff_binary_one_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "t.db"
    (tmp_path / "bin.dat").write_bytes(b"\x00\x02")
    (tmp_path / "text.dat").write_bytes(b"ok\n")
    sid = await _with_snapshots(tmp_path, db, [("bin.dat", b"\x00\x01"), ("text.dat", b"\xff\n")])
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert out == "Binary file bin.dat changed\nBinary file text.dat changed\n"
    code, out, _ = await _diff(capsys, sid, "--stat", "--db", str(db))
    assert out == "bin.dat binary\ntext.dat binary\n"


async def test_diff_no_snapshots_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    sid = await _session(tmp_path, db)
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert out == "no file changes recorded\n"


async def test_diff_skips_identical_and_absent_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    (tmp_path / "same.txt").write_text("s\n")
    (tmp_path / "made.txt").write_text("m\n")
    snaps = [("same.txt", b"s\n"), ("made.txt", None), ("gone.txt", None)]
    sid = await _with_snapshots(tmp_path, db, snaps)
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert "+m\n" in out
    assert "same.txt" not in out and "gone.txt" not in out


async def test_diff_all_identical_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    (tmp_path / "same.txt").write_text("s\n")
    sid = await _with_snapshots(tmp_path, db, [("same.txt", b"s\n")])
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert out == "no file changes remain\n"


async def test_diff_unknown_session_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    await _session(tmp_path, db)
    code, out, err = await _diff(capsys, "nope", "--db", str(db))
    assert code == 1 and out == "" and "not found" in err


async def test_diff_missing_workspace_root_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    sid = await _with_snapshots(ws, db, [("a.py", b"x\n")])
    ws.rmdir()
    code, _, err = await _diff(capsys, sid, "--db", str(db))
    assert code == 1 and "does not exist" in err


async def test_diff_skips_symlink_outside_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "secret.txt").write_text("secret\n")
    sid = await _with_snapshots(ws, db, [("link.txt", b"a\n")])
    os.symlink(tmp_path / "secret.txt", ws / "link.txt")
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert out == "skipped link.txt: outside the workspace\n"


async def test_diff_skips_file_over_size_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tether.diff.MAX_BYTES", 4)
    db = tmp_path / "t.db"
    (tmp_path / "big.txt").write_text("x" * 10)
    sid = await _with_snapshots(tmp_path, db, [("big.txt", b"x")])
    code, out, _ = await _diff(capsys, sid, "--db", str(db))
    assert code == 0
    assert out == "skipped big.txt: larger than 4 bytes\n"


def test_missing_targets_lists_new_files_only(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink(tmp_path / "outside.txt", ws / "link.txt")
    assert missing_targets("edit write ../outside.txt", ws) == []
    assert missing_targets("edit write link.txt", ws) == []
    assert missing_targets("edit write new.txt", ws) == ["new.txt"]
