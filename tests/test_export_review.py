"""`tether export` review fixes: backticks cannot break the Markdown; notes are Unreleased."""

from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.export import to_markdown
from tether.sandbox import SandboxPolicy

ROOT = Path(__file__).resolve().parents[1]


async def test_fences_survive_backticks_in_stdin_and_output(tmp_path: Path) -> None:
    body = "line\n```\nnot the end\n"
    provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd="edit write n.md", stdin=body)),
            ModelResponse(content="", action=ActionCall(cmd="cat n.md")),
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok")),
        ]
    )
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash", "edit"],
        provider=provider,
        max_steps=5,
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    rec = await h.run("g")
    md = to_markdown(h.store, rec.id)
    assert md.count("not the end") == 2
    # both blocks hold a ``` line, so each must open with a longer fence
    assert len(re.findall(r"^````+text$", md, flags=re.M)) >= 2, md


def test_release_note_is_under_unreleased() -> None:
    notes = (ROOT / "docs" / "release-notes.md").read_text()
    assert "tether export" in notes
