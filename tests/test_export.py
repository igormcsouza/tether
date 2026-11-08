"""`tether export <id>`: a session as a Markdown transcript (acceptance tests, written first)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.cli import _async_main
from tether.export import to_markdown
from tether.sandbox import SandboxPolicy


async def _session(tmp_path: Path, out_cmd: str = "echo hi") -> tuple[Harness, str]:
    provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd=out_cmd)),
            ModelResponse(
                content="", action=ActionCall(cmd="edit write notes.txt", stdin="line one\n")
            ),
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="final answer")),
        ]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash", "edit"],
        provider=provider,
        max_steps=5,
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    rec = await h.run("say hi and take notes")
    return h, rec.id


async def test_markdown_has_header_steps_and_result(tmp_path: Path) -> None:
    h, sid = await _session(tmp_path)
    md = to_markdown(h.store, sid)
    assert md.startswith(f"# Session {sid}\n")
    assert "say hi and take notes" in md
    assert "COMPLETED" in md
    assert "## Step 1" in md and "## Step 2" in md
    assert "`echo hi`" in md
    assert "hi" in md.split("## Step 1", 1)[1].split("## Step 2", 1)[0]
    assert "line one" in md  # stdin of the edit is shown
    assert md.rstrip().endswith("final answer")
    assert "## Result" in md


async def test_long_output_is_cut(tmp_path: Path) -> None:
    h, sid = await _session(tmp_path, out_cmd="python3 -c \"print('x' * 5000)\"")
    md = to_markdown(h.store, sid)
    assert "x" * 2000 in md
    assert "x" * 2500 not in md
    assert "chars cut]" in md


def test_unknown_session_raises(tmp_path: Path) -> None:
    h = Harness(db_path=tmp_path / "t.db")
    with pytest.raises(KeyError):
        to_markdown(h.store, "ses_nope")


async def test_cli_prints_and_writes_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    h, sid = await _session(tmp_path)
    db = str(tmp_path / "t.db")
    assert await _async_main(["export", sid, "--db", db]) == 0
    assert capsys.readouterr().out.startswith(f"# Session {sid}")
    out = tmp_path / "s.md"
    assert await _async_main(["export", sid, "--db", db, "--out", str(out)]) == 0
    assert out.read_text().startswith(f"# Session {sid}")
    assert str(out) in capsys.readouterr().out


async def test_cli_unknown_id_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    Harness(db_path=tmp_path / "t.db")
    assert await _async_main(["export", "ses_nope", "--db", str(tmp_path / "t.db")]) == 1
    assert "not found" in capsys.readouterr().err
