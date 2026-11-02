"""Read-only dumps are not edits; observations stay while the window has room (ladder, 2026-11-02).

Mistral-large-4 dumped the same files in `for f in ...; do cat` loops for 30 steps: tether counted
every dump as a change (no explore nudge, a false green gate) and folded each one after two turns,
so the model forgot what it had read and read it again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.context import ContextAssembler
from tether.harness import is_quiet
from tether.sandbox import SandboxPolicy
from tether.store import SQLiteStore


@pytest.mark.parametrize(
    ("cmd", "quiet"),
    [
        ('for f in a.py b.py; do echo "=== $f ==="; cat "$f"; done', True),
        ("cat a.py 2>/dev/null; ls", True),
        ('find / -name x -not -path "/proc/*" 2>/dev/null | head', True),
        ("pwd; ls -la; which python3", True),
        ('cat "a;b.py"', True),
        ("cd shop && python3 -m unittest discover", True),
        ("cat a.py; rm -f a.py", False),
        ("echo done; touch x", False),
        ("cat a.py > b.py", False),
        ("for f in *.py; do sed -i s/a/b/ $f; done", False),
        ("cat a.py; python3 -m shop.cli report", False),
    ],
)
def test_read_only_means_every_statement_is_read_only(cmd: str, quiet: bool) -> None:
    assert is_quiet(cmd) is quiet


async def test_read_dumps_in_loops_do_not_count_as_changes(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("X = 1\n", encoding="utf-8")
    cmds = [f"bash for f in a.py; do cat $f; echo {i}; done" for i in range(13)]
    steps = [ModelResponse(content="", action=ActionCall(cmd=c), prompt_tokens=10) for c in cmds]
    provider = FakeScriptedProvider(
        [*steps, ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))]
    )
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=["bash"],
        sandbox=SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False),
        provider=provider,
    )
    session = await harness.run("goal")
    outs = "\n".join(t.content for t in harness.store.get_turns(session.id) if t.role == "tool")
    assert "[NUDGE]" in outs  # #127: 12 reads and no edit


def _text(tmp_path: Path, sizes: list[int], ctx: int) -> str:
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    rec = store.create_session("goal")
    observations = {}
    for i, size in enumerate(sizes, start=1):
        cmd = f"bash ls dir{i}"
        obs = store.add_observation(rec.id, step=i, cmd=cmd, raw_output="line\n" * (size // 5))
        observations[obs.id] = obs
        store.add_turn(rec.id, step=i, role="assistant", content="", tool_cmd=cmd)
        store.add_turn(rec.id, step=i, role="tool", content=obs.raw_output, obs_id=obs.id)
    step = len(sizes) + 1
    msgs = ContextAssembler(fold_after_turns=2, max_context_tokens=ctx).assemble(
        system_prompt="S",
        goal=rec.goal,
        turns=store.get_turns(rec.id),
        observations=observations,
        pins={},
        current_step=step,
    )
    return "\n".join(str(m["content"]) for m in msgs)


def test_old_observations_stay_while_the_window_is_under_half_full(tmp_path: Path) -> None:
    text = _text(tmp_path, [500, 500, 500], ctx=32768)
    assert "folded" not in text


def test_old_observations_fold_by_age_once_the_window_is_half_full(tmp_path: Path) -> None:
    text = _text(tmp_path, [4000] * 6, ctx=8192)  # ~6k tokens of 8k
    assert "[obs_1 folded" in text and "[obs_6 folded" not in text
