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
    assert "`ls` is a shell command and this session has no shell" in out[0]
    assert "`edit write <path>`" in out[0] and "--tools" not in out[0]
    assert (tmp_path / "a.txt").read_text() == "ok\n"  # `>>` runs as `edit append` (#34)
    assert "`ls` is a shell command" in out[2] and not (tmp_path / "c.txt").exists()
    out = await _run(tmp_path, [("echo ok > b.txt", None)], ["edit", "bash"])
    assert (tmp_path / "b.txt").read_text() == "ok\n"  # real shell, not the translation


async def test_a_cd_into_a_missing_dir_is_skipped(tmp_path: Path) -> None:
    """#79: `cd /testbed && python3 -m unittest` cost qwen3.5:9b a step in 3 of 6 paasio runs."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.txt").write_text("in sub")
    out = await _run(
        tmp_path,
        [("cd /testbed && echo here", None), ("cd sub && cat x.txt", None)],
        ["bash"],
    )
    assert out[0].startswith("[`cd /testbed` skipped: no such directory") and "here" in out[0]
    assert "in sub" in out[1] and "skipped" not in out[1]  # a real dir is entered as before


def test_echo_flags_are_read_not_written() -> None:
    """web task: `echo -e "a\\nb" > ruff.md` wrote a literal `-e a\\nb`."""
    from tether.multiplexer import _as_edit

    assert _as_edit(["echo", "-e", "v: 1\\ndate: 2"], None) is None  # no redirect: not a write
    assert _as_edit(["echo", "-e", "v: 1\\ndate: 2", ">", "r.md"], None) == (
        ["edit", "write", "r.md"],
        "v: 1\ndate: 2\n",
    )
    assert _as_edit(["echo", "-n", "x", ">>", "r.md"], None) == (["edit", "append", "r.md"], "x")
    assert _as_edit(["echo", "a\\nb", ">", "r.md"], None) == (["edit", "write", "r.md"], "a\\nb\n")


async def test_curl_without_bash_points_to_web_fetch(tmp_path: Path) -> None:
    """web task: qwen3.5:9b typed `curl`, `grep`, `python3` 8 times when told how to enable bash."""
    out = await _run(tmp_path, [("curl -s https://pypi.org/pypi/ruff/json", None)], ["web", "edit"])
    assert "`curl` is a shell command and this session has no shell" in out[0]
    assert "`web fetch <url>#/key/path`" in out[0]
    disabled = await _run(tmp_path, [("agent spawn x", None)], ["edit"])
    assert "`agent` is disabled" in disabled[0] and "--tools" in disabled[0]  # Rule 4 item 3


async def test_tool_colon_verb_runs_as_tool_verb(tmp_path: Path) -> None:
    """web task: qwen3.5:9b typed `web:search q` and `web:fetch u` 5 times."""
    (tmp_path / "a.txt").write_text("hi\n")
    out = await _run(tmp_path, [("edit:view a.txt", None), ("nope:view a.txt", None)], ["edit"])
    assert "hi" in out[0]
    assert "nope:view" in out[1]  # not an enabled tool: left as typed


async def test_shell_keywords_run_through_bash(tmp_path: Path) -> None:
    """collect task: `for f in tether/*.py; do wc -l "$f"; done` answered `unknown command`."""
    (tmp_path / "a.py").write_text("x = 1\n")
    calls = [('for f in *.py; do wc -l "$f"; done', None), ("if true; then echo yes; fi", None)]
    out = await _run(tmp_path, calls, ["bash"])
    assert "1 a.py" in out[0] and "yes" in out[1]


async def test_a_loop_after_a_write_names_the_file_and_asks_for_done(tmp_path: Path) -> None:
    """collect task: told "write the file the task asked for" after writing it, qwen3.5:9b
    re-read it until a restart; replayed, 0 of 6 next steps called `done` vs 3 of 6 with this."""
    calls = [("edit write out.md", "| a | 1 |\n"), ("edit view out.md", None)] + [
        ("edit view out.md", None)
    ] * 2
    out = await _run(tmp_path, calls, ["edit"])
    loop = next(o for o in out if o.startswith("[LOOP DETECTED]"))
    assert "You already wrote out.md" in loop and 'act("done"' in loop
    assert "write the file the task asked for" not in loop
