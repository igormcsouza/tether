# A bash command that leaves a Python file unparsable is undone, and the model is told (F5).
# Local models patch files with sed -i, heredocs and python scripts; one wrong escape left a file
# that no longer parsed, and every later test run failed on import. The file goes back to the
# bytes it had before the command, and the observation says so.

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, unchanged
from tether.sandbox import SandboxPolicy

GOOD = "def f(x):\n    return x + 1\n"
BROKEN = "def f(x):\n    return x +\n"
ERR = SyntaxError("invalid syntax", ("m.py", 2, 1, "x"))
PRINT = "printf x > m.py"


def test_a_python_file_that_stopped_parsing_is_reverted(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(BROKEN)
    found = unchanged.broken_by_command(PRINT, {"m.py": GOOD.encode()}, tmp_path)
    assert [(rel, old) for rel, old, _ in found] == [("m.py", GOOD.encode())]
    assert isinstance(found[0][2], SyntaxError)


def test_a_file_that_did_not_parse_before_is_not_reverted(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(BROKEN)
    assert unchanged.broken_by_command(PRINT, {"m.py": BROKEN.encode()}, tmp_path) == []
    (tmp_path / "m.py").write_text(GOOD)
    assert unchanged.broken_by_command(PRINT, {"m.py": BROKEN.encode()}, tmp_path) == []


def test_a_file_the_command_created_is_not_reverted(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(BROKEN)
    assert unchanged.broken_by_command(PRINT, {}, tmp_path) == []


def test_a_non_python_file_is_not_reverted(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text(BROKEN)
    before = {"notes.txt": GOOD.encode()}
    assert unchanged.broken_by_command("printf x > notes.txt", before, tmp_path) == []


def test_a_file_that_parses_after_the_command_is_not_reverted(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def f(x):\n    return x + 2\n")
    assert unchanged.broken_by_command(PRINT, {"m.py": GOOD.encode()}, tmp_path) == []


def test_a_deleted_file_is_not_reverted(tmp_path: Path) -> None:
    assert unchanged.broken_by_command(PRINT, {"m.py": GOOD.encode()}, tmp_path) == []


def test_edit_commands_are_left_to_edit(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(BROKEN)
    before = {"m.py": GOOD.encode()}
    assert unchanged.broken_by_command("edit write m.py", before, tmp_path) == []
    assert unchanged.broken_by_command("bash edit replace m.py", before, tmp_path) == []


def test_revert_notes_name_at_most_three_files() -> None:
    found = [(f"f{i}.py", GOOD.encode(), ERR) for i in range(4)]
    text = unchanged.revert_notes(found)
    lines = text.splitlines()
    named = [line.split("`")[1] for line in lines if line.startswith("[REVERTED] `")]
    assert named == ["f0.py", "f1.py", "f2.py"]
    assert "1 more" in text
    assert unchanged.revert_notes([]) == ""


def test_each_revert_line_is_at_most_300_chars() -> None:
    long = SyntaxError("x" * 500, ("m.py", 2, 1, "x"))
    text = unchanged.revert_notes([("m.py", GOOD.encode(), long)])
    assert text.startswith("\n[REVERTED] `m.py` no longer parsed")
    assert all(len(line) <= 300 for line in text.splitlines())


def _policy(root: Path) -> SandboxPolicy:
    return SandboxPolicy(workspace_root=root, use_kernel_sandbox=False)


async def test_a_bash_command_that_breaks_a_python_file_is_undone(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(GOOD)
    cmds = ["cat > m.py <<EOF\n" + BROKEN + "EOF", "ls"]
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

    assert (tmp_path / "m.py").read_text() == GOOD
    seen = "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[1])
    assert "[REVERTED] `m.py` no longer parsed after this command" in seen


def test_named_python_files_finds_sed_i_target(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(GOOD)
    cmd = "sed -i 's/x/y/' m.py"
    assert unchanged.named_python_files(cmd, tmp_path) == {"m.py": GOOD.encode()}


def test_named_python_files_finds_a_path_inside_python_code(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(GOOD)
    cmd = "python3 - <<'EOF'\nsrc = open('pkg/m.py').read()\nEOF"
    assert unchanged.named_python_files(cmd, tmp_path) == {"pkg/m.py": GOOD.encode()}


def test_named_python_files_ignores_outside_and_missing(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (tmp_path / "outside.py").write_text(GOOD)
    cmd = "sed -i 's/x/y/' ../outside.py missing.py"
    assert unchanged.named_python_files(cmd, root) == {}


def test_named_python_files_is_capped_at_32(tmp_path: Path) -> None:
    names = [f"f{i}.py" for i in range(40)]
    for name in names:
        (tmp_path / name).write_text(GOOD)
    cmd = "sed -i 's/x/y/' " + " ".join(names)
    assert len(unchanged.named_python_files(cmd, tmp_path)) == 32


async def _drive(tmp_path: Path, cmds: list[str]) -> FakeScriptedProvider:
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
    return provider


def _seen(provider: FakeScriptedProvider) -> str:
    return "\n".join(str(m.get("content") or "") for m in provider.recorded_calls[1])


async def test_a_sed_i_that_breaks_a_python_file_is_undone(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(GOOD)
    provider = await _drive(tmp_path, ["sed -i 's/return/retrun (/' m.py", "ls"])
    assert (tmp_path / "m.py").read_text() == GOOD
    assert _seen(provider).count("[REVERTED] `m.py` no longer parsed") == 1


async def test_a_python_heredoc_that_breaks_a_python_file_is_undone(tmp_path: Path) -> None:
    # the file holds a literal backslash-n in an f-string; the script turns it into a newline
    before_text = 'msg = f"a' + chr(92) + 'nb {1}"' + chr(10)
    (tmp_path / "m.py").write_text(before_text)
    script = (
        "python3 - <<'EOF'"
        + chr(10)
        + "p = 'm.py'"
        + chr(10)
        + "s = open(p).read().replace(chr(92) + 'n', chr(10))"
        + chr(10)
        + "open(p, 'w').write(s)"
        + chr(10)
        + "EOF"
    )
    provider = await _drive(tmp_path, [script, "ls"])
    assert (tmp_path / "m.py").read_text() == before_text
    assert _seen(provider).count("[REVERTED] `m.py` no longer parsed") == 1


async def test_a_sed_i_that_keeps_a_python_file_parsable_is_not_reverted(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(GOOD)
    provider = await _drive(tmp_path, ["sed -i 's/1/2/' m.py", "ls"])
    assert (tmp_path / "m.py").read_text() == GOOD.replace("+ 1", "+ 2")
    assert "[REVERTED]" not in _seen(provider)
