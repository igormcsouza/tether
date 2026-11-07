"""With `edit` on and `bash` off, plain shell file reads and writes run as `edit`.

In the v0.2.17 release check, `--tools edit` and "Create hello.txt containing ok": qwen3.5:9b tried
`echo ok > hello.txt`, `printf`, `cat` and `ls` 10 times (each `unknown command`) and wrote the
file at step 12 of 15.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy


async def _run(tmp_path: Path, calls: list[tuple[str, str | None]], tools: list[str]) -> list[str]:
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd=c, stdin=s)) for c, s in calls]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=tools,
        provider=provider,
        max_steps=len(calls),
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    session = await h.run("goal")
    return [t.content for t in h.store.get_turns(session.id) if t.role == "tool"]


async def test_shell_writes_and_reads_run_as_edit(tmp_path: Path) -> None:
    out = await _run(
        tmp_path,
        [
            ("echo ok > hello.txt", None),
            ("printf 'a\\nb' > two.txt", None),
            ("cat > three.txt << 'EOF'\nx = 1\nEOF", None),
            ("bash echo hi there > four.txt", None),
            ("cat hello.txt", None),
        ],
        ["edit"],
    )
    assert (tmp_path / "hello.txt").read_text() == "ok\n"
    assert (tmp_path / "two.txt").read_text() == "a\nb"
    assert (tmp_path / "three.txt").read_text().strip() == "x = 1"
    assert (tmp_path / "four.txt").read_text() == "hi there\n"
    assert "ok" in out[4] and "unknown command" not in "".join(out)


async def test_other_commands_point_to_edit_and_bash_is_untouched(tmp_path: Path) -> None:
    calls = [("ls", None), ("echo ok >> a.txt", None), ("ls > c.txt", None)]
    out = await _run(tmp_path, calls, ["edit"])
    assert "unknown command `ls`" in out[0] and "`edit write <path>`" in out[0]
    assert (tmp_path / "a.txt").read_text() == "ok\n"  # `>>` runs as `edit append` (#34)
    assert "unknown command `ls`" in out[2] and not (tmp_path / "c.txt").exists()
    out = await _run(tmp_path, [("echo ok > b.txt", None)], ["edit", "bash"])
    assert (tmp_path / "b.txt").read_text() == "ok\n"  # real shell, not the translation
