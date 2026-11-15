"""A write that leaves the code as it was gets one line saying so (#173).

In one bench arm 9 of 62 whole-file rewrites changed nothing (2 byte-identical, 7 only comments
or spacing) and cost 456 s of model time; the model then ran the tests and got the same failure.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy
from tether.unchanged import NOTE_LIMIT, unchanged_note

CODE = "def f(x):\n    return x + 1\n"


def _before(rel: str, root: Path) -> dict[str, bytes]:
    return {rel: (root / rel).read_bytes()}


def test_identical_bytes_are_named(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    before = _before("m.py", tmp_path)
    note = unchanged_note(before, tmp_path)
    assert "[NUDGE]" in note and "m.py" in note and "unchanged" in note
    assert len(note) <= NOTE_LIMIT


def test_comment_and_spacing_changes_in_python_are_the_same_code(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    before = _before("m.py", tmp_path)
    (tmp_path / "m.py").write_text("# add one\ndef f(x):\n\n    return x+1  # same\n")
    note = unchanged_note(before, tmp_path)
    assert "m.py" in note and "comments" in note
    assert len(note) <= NOTE_LIMIT


def test_a_real_change_has_no_note(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    (tmp_path / "notes.txt").write_text("a b\n")
    before = _before("m.py", tmp_path)
    (tmp_path / "m.py").write_text(CODE.replace("+ 1", "+ 2"))
    assert unchanged_note(before, tmp_path) == ""
    # outside Python only bytes count: spacing is a change
    before = _before("notes.txt", tmp_path)
    (tmp_path / "notes.txt").write_text("a  b\n")
    assert unchanged_note(before, tmp_path) == ""


def test_a_deleted_or_broken_file_has_no_note(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    before = _before("m.py", tmp_path)
    (tmp_path / "m.py").write_text("def f(x:\n")  # syntax error: a change
    assert unchanged_note(before, tmp_path) == ""
    (tmp_path / "m.py").unlink()
    assert unchanged_note(before, tmp_path) == ""


def _policy(root: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)


async def test_the_note_follows_a_rewrite_that_changed_nothing(tmp_path: Path) -> None:
    write = f"cat > m.py << 'EOF'\n{CODE}EOF"
    # an identical command is caught by the repeat guard; a comment makes it a new command
    cmds = [write, f"cat > m.py << 'EOF'\n# try again\n{CODE}EOF", "ls"]
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd=c)) for c in cmds]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=provider,
        max_steps=len(cmds),
        sandbox=_policy(tmp_path),
    )
    await h.run("goal")

    def seen(call: int) -> str:
        return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])

    assert (tmp_path / "m.py").read_text().startswith("# try again\ndef f(x):")
    assert "unchanged" not in seen(1)  # the first write created the file
    assert "[NUDGE]" in seen(2) and "m.py" in seen(2).split("unchanged", 1)[0][-200:]
