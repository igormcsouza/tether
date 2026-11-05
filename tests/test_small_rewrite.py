"""A whole-file rewrite that changed a few lines points to `edit replace`, once per file (#173).

In arm E (main, 10 failed runs) 24 of 51 rewrites of an existing file changed at most 20% of its
lines and cost 1123 s of model time: the model types the whole file again to change two lines.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy
from tether.unchanged import NOTE_LIMIT, small_change_note, snapshot

LINES = [f"def f{i}(x):\n    return x + {i}\n" for i in range(15)]
CODE = "".join(LINES)  # 30 lines


def _two_lines_changed() -> str:
    return CODE.replace("x + 3\n", "x - 3\n").replace("x + 7\n", "x - 7\n")


def test_a_small_whole_file_rewrite_points_to_edit_replace(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    cmd = "edit write m.py"
    before = snapshot(cmd, tmp_path)
    (tmp_path / "m.py").write_text(_two_lines_changed())
    note = small_change_note(cmd, before, tmp_path, set())
    assert "[NUDGE]" in note and "2 of 30" in note and "edit replace m.py" in note
    assert len(note) <= NOTE_LIMIT


def test_a_heredoc_rewrite_counts_too(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    cmd = f"cat > m.py << 'EOF'\n{_two_lines_changed()}EOF"
    before = snapshot(cmd, tmp_path)
    (tmp_path / "m.py").write_text(_two_lines_changed())
    assert "edit replace m.py" in small_change_note(cmd, before, tmp_path, set())


def test_the_note_is_given_once_per_file(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    hinted: set[str] = set()
    before = snapshot("edit write m.py", tmp_path)
    (tmp_path / "m.py").write_text(_two_lines_changed())
    assert small_change_note("edit write m.py", before, tmp_path, hinted)
    assert hinted == {"m.py"}
    before = snapshot("edit write m.py", tmp_path)
    (tmp_path / "m.py").write_text(CODE)
    assert small_change_note("edit write m.py", before, tmp_path, hinted) == ""


def test_no_note_for_a_big_change_a_short_file_or_a_partial_write(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    before = snapshot("edit write m.py", tmp_path)
    (tmp_path / "m.py").write_text(CODE.replace("x +", "x *"))  # every return line: 15 of 30
    assert small_change_note("edit write m.py", before, tmp_path, set()) == ""
    # a short file is cheap to rewrite
    (tmp_path / "s.py").write_text("".join(LINES[:5]))
    before = snapshot("edit write s.py", tmp_path)
    (tmp_path / "s.py").write_text("".join(LINES[:5]).replace("x + 3", "x - 3"))
    assert small_change_note("edit write s.py", before, tmp_path, set()) == ""
    # edit replace and >> already write only part of the file
    for cmd in ("edit replace m.py --lines 7:8", "echo '# x' >> m.py"):
        (tmp_path / "m.py").write_text(CODE)
        before = snapshot(cmd, tmp_path)
        (tmp_path / "m.py").write_text(_two_lines_changed())
        assert small_change_note(cmd, before, tmp_path, set()) == ""
    # no change at all is the unchanged note's job, and a deleted file is no rewrite
    (tmp_path / "m.py").write_text(CODE)
    before = snapshot("edit write m.py", tmp_path)
    assert small_change_note("edit write m.py", before, tmp_path, set()) == ""
    (tmp_path / "m.py").unlink()
    assert small_change_note("edit write m.py", before, tmp_path, set()) == ""


async def test_the_harness_adds_the_note_once(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(CODE)
    once, twice = _two_lines_changed(), CODE.replace("x + 9\n", "x - 9\n")
    cmds = [f"cat > m.py << 'EOF'\n{once}EOF", f"cat > m.py << 'EOF'\n{twice}EOF", "ls"]
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd=c)) for c in cmds]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=provider,
        max_steps=len(cmds),
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    await h.run("goal")

    def seen(call: int) -> str:
        return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[call])

    assert "edit replace m.py" in seen(1)
    assert seen(2).count("edit replace m.py") == 1  # the second small rewrite gets no new note
