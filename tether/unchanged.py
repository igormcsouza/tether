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

# `edit` warns about a file that stops parsing on its own, so it is not reverted here
_EDIT = re.compile(r"^(?:bash\s+)?edit\s+(?:write|replace|append)\s+(\S+)")


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


REVERT_FILES = 3  # files named in the revert notes of one command
REVERT_MSG = 80  # chars of the SyntaxError message in a revert note
REVERT_LINE = 300  # max chars of one revert line


def _syntax_error(data: bytes) -> SyntaxError | None:
    try:
        ast.parse(data)
    except (SyntaxError, ValueError) as err:
        return err if isinstance(err, SyntaxError) else None
    return None


def broken_by_command(
    cmd: str, before: dict[str, bytes], root: Path
) -> list[tuple[str, bytes, SyntaxError]]:
    """Python files that parsed before `cmd` and do not parse after it (F5).

    Returns (path, old bytes, error) for each. Edit commands are left to `edit`, which warns on
    its own. Not returned: a file that did not parse before, a file the command created or
    deleted, a non-.py file, and a file that still parses.
    """
    if _EDIT.match(cmd.partition("\n")[0]):
        return []
    found: list[tuple[str, bytes, SyntaxError]] = []
    for rel, old in before.items():
        new = _current(rel, root)
        if not rel.endswith(".py") or new is None or _syntax_error(old) is not None:
            continue
        if (err := _syntax_error(new)) is not None:
            found.append((rel, old, err))
    return found


def revert_notes(found: list[tuple[str, bytes, SyntaxError]]) -> str:
    """One [REVERTED] line per file (at most REVERT_FILES), each at most REVERT_LINE chars."""
    lines = [
        f"\n[REVERTED] `{rel}` no longer parsed after this command "
        f"({err.msg[:REVERT_MSG]}, line {err.lineno}); it is back as it was before the command. "
        f"Make the change again in smaller steps, e.g. `edit replace {rel} --lines a:b`."[
            :REVERT_LINE
        ]
        for rel, _, err in found[:REVERT_FILES]
    ]
    if len(found) > REVERT_FILES:
        lines.append(f"\n[REVERTED] {len(found) - REVERT_FILES} more file(s) reverted too.")
    return "".join(lines)
