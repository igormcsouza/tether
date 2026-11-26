"""Files the user had before the session come back when a command deletes them (#350).

Coding Ladder shell-5, qwen3.5:9b: after a passing fix the model ran `rm -rf data && bash
backup.sh` to try its "data/ is missing" branch and the user's data/ folder was gone.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy


async def _run(tmp_path: Path, goal: str, calls: list[str]) -> list[str]:
    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd=c)) for c in calls]
    )
    h = Harness(
        db_path=tmp_path / ".tether" / "t.db",
        tools=["bash"],
        provider=provider,
        max_steps=len(calls),
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    session = await h.run(goal)
    return [t.content for t in h.store.get_turns(session.id) if t.role == "tool"]


def _data(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    for i in range(4):
        (tmp_path / "data" / f"f {i}.txt").write_text(f"row {i}\n")


async def test_deleted_user_files_come_back(tmp_path: Path) -> None:
    _data(tmp_path)
    out = await _run(tmp_path, "Fix backup.sh", ["rm -rf data && ls data || echo gone"])
    assert "gone" in out[0]  # the command itself saw data/ missing
    assert [(tmp_path / "data" / f"f {i}.txt").read_text() for i in range(4)] == [
        f"row {i}\n" for i in range(4)
    ]
    assert "[KEPT] `data/f 0.txt`, `data/f 1.txt`, `data/f 2.txt` and 1 more" in out[0]


async def test_a_goal_that_asks_to_delete_keeps_them_deleted(tmp_path: Path) -> None:
    _data(tmp_path)
    out = await _run(tmp_path, "Remove the data folder", ["rm -rf data"])
    assert not (tmp_path / "data").exists() and "[KEPT]" not in out[0]


async def test_files_the_session_created_stay_deleted(tmp_path: Path) -> None:
    out = await _run(tmp_path, "Fix it", ["echo x > tmp.txt", "rm tmp.txt"])
    assert not (tmp_path / "tmp.txt").exists() and "[KEPT]" not in "".join(out)
