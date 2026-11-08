"""Edge cases of the gate pre-check: no program in the gate."""

from __future__ import annotations

from pathlib import Path

from tether.gates import precheck
from tether.sandbox import SandboxPolicy


def _policy(root: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)


def test_gate_starting_with_a_separator_is_a_parse_error(tmp_path: Path) -> None:
    msg = precheck(["&& python3 -V"], _policy(tmp_path))
    assert msg is not None and "parse" in msg


def test_semicolon_token_after_another_separator_still_splits(tmp_path: Path) -> None:
    msg = precheck(["true && true; nope-d"], _policy(tmp_path))
    assert msg is not None and "nope-d" in msg


def test_gate_with_only_assignments_is_empty(tmp_path: Path) -> None:
    assert precheck(["FOO=1 BAR=2"], _policy(tmp_path)) == "verification gate is empty"
