"""Pre-check verification gate commands before a session starts (#82)."""

from __future__ import annotations

import re
import shlex
import shutil
from pathlib import Path

from tether.sandbox import SandboxPolicy

SHELL_BUILTINS = {"cd", "test", "[", "true", "false", "echo", "export", "source", ".", "exit"}

_SEPARATORS = {"&&", "||", ";", "|"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _program(tokens: list[str]) -> str | None:
    """Return the program of a segment, skipping NAME=value tokens."""
    for tok in tokens:
        if _ASSIGNMENT.match(tok):
            continue
        return tok
    return None


def _split_segments(tokens: list[str]) -> list[list[str]]:
    """Split tokens into segments on &&, ||, ;, |. Also split tokens ending with ;."""
    segments: list[list[str]] = []
    current: list[str] = []

    for tok in tokens:
        # If token ends with ;, split it
        if tok.endswith(";"):
            # First add the part before ; to current segment
            if tok[:-1]:
                current.append(tok[:-1])
            # A trailing ; ends the segment
            if current:
                segments.append(current)
                current = []
            continue

        # Check if this token is a separator
        if tok in _SEPARATORS:
            # If we hit a separator, finalize current segment if any
            if current:
                segments.append(current)
                current = []
            continue

        current.append(tok)

    # Don't forget the last segment
    if current:
        segments.append(current)

    return segments


def precheck(commands: list[str], policy: SandboxPolicy) -> str | None:
    """Return an error message for the first bad gate command, or None if all look runnable."""
    root = Path(policy.workspace_root or Path.cwd())
    for cmd in commands:
        if not cmd.strip():
            return "verification gate is empty"
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            return f"cannot parse verification gate `{cmd}`: {exc}"
        if tokens and tokens[0] in _SEPARATORS:
            return f"cannot parse verification gate `{cmd}`: starts with `{tokens[0]}`"

        segments = _split_segments(tokens)

        # Check if any segment has a program
        has_program = False
        for seg in segments:
            # Skip segments with no program
            prog = _program(seg)
            if prog is None:
                continue
            has_program = True
            if prog in SHELL_BUILTINS:
                continue
            if "/" in prog:
                # root / prog is prog itself when prog is absolute
                if not (root / prog).exists():
                    return f"verification gate `{cmd}`: `{prog}` not found"
                continue
            if shutil.which(prog) is None:
                hint = " (install it or fix the --verify command)"
                return f"verification gate `{cmd}`: `{prog}` not found{hint}"

        if not has_program:
            return "verification gate is empty"

    return None
