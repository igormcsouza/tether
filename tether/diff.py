"""`tether diff <session_id>`: what a session changed in its files, against the first bytes it saw.

The snapshots come from the write-tracking loop in the harness (`file_snapshots`); the current
files are read from disk, so the output changes if they are edited later.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from tether.store import SQLiteStore
from tether.unchanged import MAX_BYTES


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


def render_diff(store: SQLiteStore, session_id: str, root: Path, stat: bool) -> tuple[str, int]:
    """Text to print and exit code. Errors come back as text with exit code 1."""
    if not root.is_dir():
        return f"Error: workspace root {root} does not exist.\n", 1
    snapshots = store.list_snapshots(session_id)
    if not snapshots:
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
    return (text or "no file changes remain\n"), 0
