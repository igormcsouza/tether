"""`tether diff <session_id>`: what a session changed in its files, against the first bytes it saw.

The snapshots come from the write-tracking loop in the harness (`file_snapshots`); the current
files are read from disk, so the output changes if they are edited later.
"""

from __future__ import annotations

import difflib
import os
from contextlib import suppress
from pathlib import Path

from tether.store import SQLiteStore
from tether.unchanged import MAX_BYTES

_SKIP_DIRS = {"__pycache__", "node_modules"}  # never the user's work
_LISTED = 20  # untracked paths named in full; the rest are counted
SCAN_LIMIT = 2000  # files the diff-time walk considers


def _is_binary(data: bytes) -> bool:
    if b"\0" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _file_diff(rel: str, old: bytes | None, new: bytes | None, stat: bool) -> str:
    """Unified diff (or a `--stat` line) for one path; "" when nothing changed.

    None means the file did not exist on that side.
    """
    if old == new:
        return ""
    if any(side is not None and _is_binary(side) for side in (old, new)):
        return f"{rel} binary\n" if stat else f"Binary file {rel} changed\n"
    diff = list(
        difflib.unified_diff(
            (old or b"").decode("utf-8").splitlines(keepends=True),
            (new or b"").decode("utf-8").splitlines(keepends=True),
            f"a/{rel}",
            f"b/{rel}",
        )
    )
    if not stat:
        return "".join(diff)
    body = diff[2:]  # skip the ---/+++ headers
    added = sum(1 for line in body if line.startswith("+"))
    removed = sum(1 for line in body if line.startswith("-"))
    return f"{rel} +{added} -{removed}\n"


def untracked_changes(
    root: Path, start: float, end: float, known: set[str], skip: set[Path]
) -> tuple[list[str], bool]:
    """Files in `root` modified inside [start, end] with no snapshot, and whether the walk bailed.

    Writes by commands tether could not track show up here as an mtime inside the session window.
    Dot-directories, `__pycache__` and `node_modules` are skipped, and so are symlinks and the
    database files. Stops after SCAN_LIMIT entries and reports `bailed`.
    """
    base = root.resolve()
    found: list[str] = []
    entries = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
        for name in filenames:
            entries += 1
            if entries > SCAN_LIMIT:
                return sorted(found), True
            path = Path(dirpath) / name
            if path.is_symlink() or path in skip:
                continue
            with suppress(OSError):
                if start <= path.stat().st_mtime <= end:
                    rel = os.path.normpath(path.relative_to(base).as_posix())
                    if rel not in known:
                        found.append(rel)
    return sorted(found), False


def _untracked_note(paths: list[str], bailed: bool) -> str:
    """One line per kind of write tether could not attribute; "" when there is none."""
    note = ""
    if paths:
        more = f", +{len(paths) - _LISTED} more" if len(paths) > _LISTED else ""
        noun = "file" if len(paths) == 1 else "files"
        shown = ", ".join(paths[:_LISTED])
        note += f"{len(paths)} {noun} changed by commands tether could not track: {shown}{more}\n"
    if bailed:
        note += (
            f"workspace has more than {SCAN_LIMIT} files: "
            "changes by untracked commands were not checked\n"
        )
    return note


def render_diff(store: SQLiteStore, session_id: str, root: Path, stat: bool) -> tuple[str, int]:
    """Text to print and exit code. Errors come back as text with exit code 1."""
    if not root.is_dir():
        return f"Error: workspace root {root} does not exist.\n", 1
    snapshots = store.list_snapshots(session_id)
    rec = store.get_session(session_id)
    untracked: list[str] = []
    bailed = False
    if rec is not None:
        known = {os.path.normpath(rel) for rel, _ in snapshots}
        db = store.db_path
        skip = {db, Path(f"{db}-wal"), Path(f"{db}-shm")}
        end = rec.updated_at + 1.0  # slack for mtime granularity
        untracked, bailed = untracked_changes(root, rec.created_at, end, known, skip)
    note = _untracked_note(untracked, bailed)
    if not snapshots and not note:
        return "no file changes recorded\n", 0
    base = root.resolve()
    parts = []
    for rel, old in snapshots:
        path = (root / rel).resolve()
        if not path.is_relative_to(base):
            parts.append(f"skipped {rel}: outside the workspace\n")
            continue
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            parts.append(f"skipped {rel}: larger than {MAX_BYTES} bytes\n")
            continue
        new = path.read_bytes() if path.is_file() else None
        parts.append(_file_diff(rel, old, new, stat))
    text = "".join(parts)
    if not text and not note:
        text = "no file changes remain\n"
    return text + note, 0
