"""Notices that ask the model to act are tagged on their tool turn, and `tether stats` shows how
often each fires and is followed (H3). The notice text itself does not change."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.sandbox import SandboxPolicy
from tether.store import SQLiteStore

WRITE = "cat > m.py << 'EOF'\ndef f():\n    return 3\nEOF"


def _act(cmd: str) -> ModelResponse:
    return ModelResponse(content="", action=ActionCall(cmd=cmd))


@pytest.fixture
def tight_nudges(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("QUIET_NUDGE_STEPS", "EXPLORE_NUDGE_STEPS"):
        monkeypatch.setattr(f"tether.harness.{name}", 2)
    for name in ("QUIET_NUDGE_EVERY", "EXPLORE_NUDGE_EVERY"):
        monkeypatch.setattr(f"tether.harness.{name}", 1)


async def _run(tmp_path: Path, cmds: list[str]) -> Path:
    h = Harness(
        db_path=tmp_path / "t.db",
        tools=["bash"],
        provider=FakeScriptedProvider([_act(c) for c in cmds]),
        max_steps=len(cmds),
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
    )
    await h.run("goal")
    return tmp_path / "t.db"


def _tool_rules(db: Path, needle: str) -> list[str]:
    with closing(sqlite3.connect(db)) as conn:
        rows = conn.execute(
            "SELECT rule FROM turns WHERE role = 'tool' AND content LIKE ?", (f"%{needle}%",)
        ).fetchall()
    return [str(r[0]) for r in rows]


async def test_quiet_nudge_turn_is_tagged(tmp_path: Path, tight_nudges: None) -> None:
    db = await _run(tmp_path, [WRITE, "ls", "pwd", "ls -a", "pwd -P"])
    rules = _tool_rules(db, "No file changes for")
    assert rules and set(rules) == {"tell:quiet"}


async def test_explore_nudge_turn_is_tagged(tmp_path: Path, tight_nudges: None) -> None:
    db = await _run(tmp_path, ["ls", "pwd", "ls -a", "pwd -P"])
    rules = _tool_rules(db, "No file changes in") + _tool_rules(db, "lookups and no answer")
    assert rules and set(rules) == {"tell:explore"}


def _seed(store: SQLiteStore, pairs: list[tuple[str, str]]) -> None:
    """One tool turn per (notice id, next command); the next assistant turn is what follows it."""
    sid = store.create_session("fix bug").id
    for step, (rule, nxt) in enumerate(pairs, start=1):
        store.add_turn(sid, step, "assistant", "act", tool_cmd="ls")
        store.add_turn(sid, step, "tool", "[NUDGE] x", rule=rule)
        store.add_turn(sid, step, "assistant", "next", tool_cmd=nxt)


def test_stats_counts_notices_fired_and_followed(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "t.db")
    _seed(
        store,
        [
            ("tell:quiet", 'done "x"'),
            ("tell:quiet", "ls"),
            ("tell:explore", "edit write m.py"),
            ("tell:explore", "ls"),
        ],
    )
    out = store.format_stats_report()
    assert "notices followed:" in out
    assert "tell:quiet: fired 2, followed 1 (50%)" in out
    assert "tell:explore: fired 2, followed 1 (50%)" in out


def test_no_notices_section_without_fired_notices(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "t.db")
    sid = store.create_session("fix bug").id
    store.add_turn(sid, 1, "assistant", "act", tool_cmd="ls")
    assert "notices followed" not in store.format_stats_report()
