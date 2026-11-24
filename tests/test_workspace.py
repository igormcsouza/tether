"""Tracker: what changed in the workspace between two looks (H2)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tether import workspace
from tether.workspace import Changes, Tracker


def _bump(path: Path) -> None:
    # a later mtime without depending on the clock's resolution
    stamp = path.stat().st_mtime_ns + 5_000_000
    os.utime(path, ns=(stamp, stamp))


def test_scan_lists_files_with_mtime_and_size(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.txt").write_text("hello")
    meta = Tracker(tmp_path).scan()
    assert set(meta) == {"a.py", os.path.join("pkg", "b.txt")}
    assert meta["a.py"][1] == 3
    assert isinstance(meta["a.py"][0], int)


@pytest.mark.parametrize(
    "skipped", [".git", ".venv", "node_modules", "__pycache__", ".tether", ".hidden"]
)
def test_scan_skips_directories(tmp_path: Path, skipped: str) -> None:
    (tmp_path / skipped).mkdir()
    (tmp_path / skipped / "f.py").write_text("x")
    (tmp_path / "keep.py").write_text("x")
    assert set(Tracker(tmp_path).scan()) == {"keep.py"}


def test_step_reports_created(tmp_path: Path) -> None:
    tracker = Tracker(tmp_path)
    tracker.scan()
    (tmp_path / "new.py").write_text("x=1")
    changes = tracker.step()
    assert changes == Changes(created=["new.py"], modified=[], deleted=[], touched=[])
    assert tracker.old("new.py") is None


def test_step_reports_modified_with_old_bytes(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    f.write_text("x=1")
    tracker = Tracker(tmp_path)
    tracker.scan()
    f.write_text("x=22")
    changes = tracker.step()
    assert changes.modified == ["f.py"]
    assert tracker.old("f.py") == b"x=1"
    # the next step starts from what was just seen
    assert tracker.step() == Changes([], [], [], [])
    assert tracker.old("f.py") is None


def test_step_reports_deleted_with_old_bytes(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    f.write_text("x=1")
    tracker = Tracker(tmp_path)
    tracker.scan()
    f.unlink()
    changes = tracker.step()
    assert changes.deleted == ["f.py"]
    assert tracker.old("f.py") == b"x=1"


def test_same_bytes_rewrite_is_touched_not_modified(tmp_path: Path) -> None:
    f = tmp_path / "f.py"
    f.write_text("x=1")
    tracker = Tracker(tmp_path)
    tracker.scan()
    _bump(f)
    changes = tracker.step()
    assert changes == Changes(created=[], modified=[], deleted=[], touched=["f.py"])


def test_nothing_changed_is_empty(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("x=1")
    tracker = Tracker(tmp_path)
    tracker.scan()
    assert not any(tracker.step())


def test_old_is_unknown_for_a_file_never_seen(tmp_path: Path) -> None:
    tracker = Tracker(tmp_path)
    tracker.scan()
    assert tracker.old("nope.py") is None


def test_big_file_is_modified_without_old_bytes(tmp_path: Path) -> None:
    f = tmp_path / "big.bin"
    f.write_bytes(b"a" * (workspace.MAX_FILE_BYTES + 1))
    tracker = Tracker(tmp_path)
    tracker.scan()
    f.write_bytes(b"b" * (workspace.MAX_FILE_BYTES + 1))
    _bump(f)
    assert tracker.step().modified == ["big.bin"]
    assert tracker.old("big.bin") is None


def test_cache_budget_is_first_come(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace, "MAX_CACHE_BYTES", 10)
    (tmp_path / "a.txt").write_bytes(b"123456")  # fits
    (tmp_path / "b.txt").write_bytes(b"123456")  # would pass 10 bytes: not kept
    tracker = Tracker(tmp_path)
    tracker.scan()
    (tmp_path / "a.txt").write_bytes(b"654321")
    (tmp_path / "b.txt").write_bytes(b"654321")
    _bump(tmp_path / "a.txt")
    _bump(tmp_path / "b.txt")
    changes = tracker.step()
    assert changes.modified == ["a.txt", "b.txt"]
    assert tracker.old("a.txt") == b"123456"
    assert tracker.old("b.txt") is None


def test_cache_budget_is_freed_when_a_file_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace, "MAX_CACHE_BYTES", 10)
    (tmp_path / "a.txt").write_bytes(b"123456")
    tracker = Tracker(tmp_path)
    tracker.scan()
    (tmp_path / "a.txt").unlink()
    tracker.step()
    (tmp_path / "c.txt").write_bytes(b"123456")
    tracker.step()
    (tmp_path / "c.txt").write_bytes(b"abcdef")
    _bump(tmp_path / "c.txt")
    tracker.step()
    assert tracker.old("c.txt") == b"123456"


def test_too_many_files_disables_the_tracker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace, "MAX_ENTRIES", 3)
    for i in range(4):
        (tmp_path / f"f{i}.txt").write_text("x")
    tracker = Tracker(tmp_path)
    assert not tracker.disabled
    tracker.scan()
    assert tracker.disabled
    assert tracker.step() == Changes([], [], [], [])


def test_exactly_the_cap_is_not_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace, "MAX_ENTRIES", 3)
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("x")
    tracker = Tracker(tmp_path)
    tracker.scan()
    assert not tracker.disabled


def test_file_vanishing_during_the_walk_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "gone.txt").write_text("x")
    real = os.stat

    def flaky(path: str | os.PathLike[str], *args: object, **kw: object) -> os.stat_result:
        if str(path).endswith("gone.txt"):
            raise FileNotFoundError(path)
        return real(path, *args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(workspace.os, "stat", flaky)
    assert set(Tracker(tmp_path).scan()) == {"a.txt"}


def test_unreadable_file_is_tracked_without_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x")
    real = Path.read_bytes

    def deny(self: Path) -> bytes:
        if self.name == "f.txt":
            raise PermissionError(str(self))
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    tracker = Tracker(tmp_path)
    assert set(tracker.scan()) == {"f.txt"}
    f.write_text("yy")
    assert tracker.step().modified == ["f.txt"]
    assert tracker.old("f.txt") is None


def test_scan_of_2000_files_is_fast(tmp_path: Path) -> None:
    for d in range(20):
        sub = tmp_path / f"d{d}"
        sub.mkdir()
        for i in range(100):
            (sub / f"f{i}.py").write_text("x = 1\n")
    tracker = Tracker(tmp_path)
    start = time.perf_counter()
    meta = tracker.scan()
    tracker.step()
    elapsed = time.perf_counter() - start
    assert len(meta) == 2000
    # one scan plus one step is two walks; this stays robust on a slow runner
    assert elapsed < 0.5


def test_a_fifo_is_not_a_file(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "a.txt").write_text("a")
    assert list(Tracker(tmp_path).scan()) == ["a.txt"]


def test_growing_past_the_cap_disables_on_a_later_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace, "MAX_ENTRIES", 1)
    (tmp_path / "a.txt").write_text("a")
    tracker = Tracker(tmp_path)
    tracker.scan()
    assert not tracker.disabled
    (tmp_path / "b.txt").write_text("b")
    assert tracker.step() == Changes([], [], [], [])
    assert tracker.disabled


def test_refresh_absorbs_the_harness_own_writes(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("one")
    gone = tmp_path / "b.txt"
    gone.write_text("b")
    tracker = Tracker(tmp_path)
    tracker.scan()
    f.write_text("two!")  # rewritten by the harness: a change of the file, not of the model
    gone.unlink()  # and a file the harness removed
    tracker.refresh(["a.txt", "b.txt"])
    assert tracker.step() == Changes([], [], [], [])


def test_secret_looking_files_are_never_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=1")
    (tmp_path / "server.pem").write_text("key")
    (tmp_path / "a.py").write_text("x = 1")
    tracker = Tracker(tmp_path)
    assert set(tracker.scan()) == {"a.py"}
    (tmp_path / ".env").write_text("TOKEN=2")
    assert tracker.step() == Changes([], [], [], [])


def test_rewrite_back_to_an_earlier_content_is_revisited(tmp_path: Path) -> None:
    # AD-50: A, B, A flips back to a content the file had; C is new; re-creating is revisited
    f = tmp_path / "report.md"
    tracker = Tracker(tmp_path)
    tracker.scan()
    f.write_text("A")
    assert tracker.step().revisited == []
    f.write_text("B")
    assert tracker.step().revisited == []
    f.write_text("A")
    third = tracker.step()
    assert third.modified == ["report.md"] and third.revisited == ["report.md"]
    f.write_text("C")
    assert tracker.step().revisited == []
    f.unlink()
    tracker.step()
    f.write_text("A")
    assert tracker.step().revisited == ["report.md"]


def test_revisit_seeds_from_the_first_look(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("first")
    tracker = Tracker(tmp_path)
    tracker.scan()
    (tmp_path / "f.txt").write_text("second")
    tracker.step()
    (tmp_path / "f.txt").write_text("first")
    assert tracker.step().revisited == ["f.txt"]


def test_oversized_file_is_never_revisited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace, "MAX_FILE_BYTES", 4)
    f = tmp_path / "big.txt"
    tracker = Tracker(tmp_path)
    tracker.scan()
    for text in ("aaaaaaaa", "bbbbbbbb", "aaaaaaaa"):
        f.write_text(text)
        assert tracker.step().revisited == []
