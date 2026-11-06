"""Name a write that left the code as it was (#173).

A small model often rewrites a whole file with the same code. `snapshot` keeps the bytes of the
files a command writes before it runs; `unchanged_note` compares them after, so the observation
can say so instead of leaving the model to run the same failing tests again.
"""

from __future__ import annotations

import ast
import re
from contextlib import suppress
from pathlib import Path

NOTE_LIMIT = 200  # max chars of the note
MAX_BYTES = 256_000  # files larger than this are not compared

_EDIT = re.compile(r"^(?:bash\s+)?edit\s+(?:write|replace)\s+(\S+)")
_REDIRECT = re.compile(r">>?\s*([\w./-]+)")
_TEE = re.compile(r"\btee\b([^|;&<>\n]*)")


def _targets(cmd: str) -> list[str]:
    """Paths `cmd` writes to, as written in it (they may be missing or outside the workspace)."""
    head = cmd.partition("\n")[0]  # a heredoc body's `a > b` is code, not a redirect
    args = [word for group in _TEE.findall(head) for word in group.split()]
    tee = [word for word in args if not word.startswith("-")]
    return _EDIT.findall(head) + _REDIRECT.findall(head) + tee


def _current(rel: str, root: Path) -> bytes | None:
    """Bytes of the existing regular file `rel` inside `root`, else None."""
    with suppress(OSError, RuntimeError, ValueError):
        base = root.resolve()
        path = (base / rel).resolve()
        if path.is_file() and path.is_relative_to(base) and path.stat().st_size <= MAX_BYTES:
            return path.read_bytes()
    return None


def _same_code(old: bytes, new: bytes) -> bool:
    try:
        return ast.dump(ast.parse(old)) == ast.dump(ast.parse(new))
    except (SyntaxError, ValueError):
        return False


def _same(rel: str, old: bytes, new: bytes) -> bool:
    """Identical bytes, or (Python only) an identical AST: comments and spacing do not count."""
    if old == new:
        return True
    return rel.endswith(".py") and _same_code(old, new)


def snapshot(cmd: str, root: Path) -> dict[str, bytes]:
    """Current bytes of the existing workspace files `cmd` writes.

    Keyed by the path as written in cmd. Write targets: `edit write <p>` / `edit replace <p>`
    (argv[1:3] after an optional leading `bash`), shell redirects `> p` / `>> p`, and
    `tee [-a] p...` arguments. Only regular files that exist now, resolve inside `root` and are
    at most MAX_BYTES are kept; anything else (run, read, new file, outside root) is left out.
    Never raises.
    """
    return {rel: data for rel in _targets(cmd) if (data := _current(rel, root)) is not None}


def unchanged_note(before: dict[str, bytes], root: Path) -> str:
    """Return a one-line note if the files in `before` still hold the same code, else "".

    - All byte-identical: "<paths> unchanged: what you wrote is what was there."
    - Else (some .py file differs only in comments or spacing, same AST): "<paths>: only comments
      or spacing changed, the code is the same."
    Both end with "The tests will fail the same way; change the logic." A non-.py file counts as
    the same code only if byte-identical. A SyntaxError or a missing file means "changed".
    Truncated to NOTE_LIMIT. Empty `before` gives "".
    """
    now = {rel: _current(rel, root) for rel in before}
    if not before or not all(
        data is not None and _same(rel, before[rel], data) for rel, data in now.items()
    ):
        return ""
    paths = ", ".join(sorted(before))
    if all(now[rel] == before[rel] for rel in before):
        what = f"{paths} unchanged: what you wrote is what was there."
    else:
        what = f"{paths}: only comments or spacing changed, the code is the same."
    note = f"\n[NUDGE] {what} The tests will fail the same way; change the logic."
    return note[:NOTE_LIMIT]
