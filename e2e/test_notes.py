"""Notes the harness appends to an observation after a write. Scripted replies, no model (#173)."""

from __future__ import annotations

from e2e.conftest import Tether

CODE = "".join(f"def f{i}(x):\n    return x + {i}\n" for i in range(15))  # 30 lines


def test_a_rewrite_with_the_same_code_is_named(tether: Tether, chaos) -> None:
    (tether.ws / "m.py").write_text(CODE)
    chaos.script(("edit write m.py", "# try again\n" + CODE), ("done", "ok"))
    r = tether.run("rewrite", "--tools", "edit")
    out = tether.tool_outputs(r["id"])[0]
    assert "[NUDGE]" in out and "only comments or spacing changed" in out


def test_a_small_whole_file_rewrite_points_to_edit_replace(tether: Tether, chaos) -> None:
    (tether.ws / "m.py").write_text(CODE)
    chaos.script(("edit write m.py", CODE.replace("x + 3\n", "x - 3\n")), ("done", "ok"))
    r = tether.run("rewrite", "--tools", "edit")
    out = tether.tool_outputs(r["id"])[0]
    assert "1 of 30 lines changed" in out and "edit replace m.py" in out
