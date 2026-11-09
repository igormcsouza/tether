"""#82 review fixes: every program in a chained gate is checked; release notes say so."""

from __future__ import annotations

from pathlib import Path

from tether.gates import precheck
from tether.sandbox import SandboxPolicy

ROOT = Path(__file__).resolve().parents[1]


def _policy(root: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)


def test_missing_program_after_and_is_reported(tmp_path: Path) -> None:
    msg = precheck(["python3 -V && no-such-tool-xyz --check"], _policy(tmp_path))
    assert msg is not None and "no-such-tool-xyz" in msg


def test_missing_program_after_a_pipe_or_semicolon_is_reported(tmp_path: Path) -> None:
    assert "nope-a" in (precheck(["true | nope-a"], _policy(tmp_path)) or "")
    assert "nope-b" in (precheck(["true; nope-b"], _policy(tmp_path)) or "")
    assert "nope-c" in (precheck(["false || nope-c"], _policy(tmp_path)) or "")


def test_chain_of_good_programs_passes(tmp_path: Path) -> None:
    assert precheck(["cd . && FOO=1 python3 -V | cat; true || echo x"], _policy(tmp_path)) is None


def test_release_notes_mention_the_precheck() -> None:
    unreleased = (ROOT / "docs" / "release-notes.md").read_text()
    assert "#82" in unreleased
