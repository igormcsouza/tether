"""Automatic fold window (#205): fold oldest-first only as far as the 50% target needs.

A fixed K folded every old observation the turn the history crossed half the window (a cliff),
so long tasks forgot what they had read and read it again. Auto mode folds just enough, never
the newest K turns or a live read (#69), and lengthens K (cap 8) for a session that re-reads.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import tether.context as context
import tether.harness as harness_mod
from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse
from tether.context import (
    ACT_TOOL_SCHEMA,
    ContextAssembler,
    estimate_messages_tokens,
    tombstone,
)
from tether.sandbox import SandboxPolicy
from tether.store import ObservationRecord, SQLiteStore, TurnRecord

Hist = tuple[list[TurnRecord], dict[str, ObservationRecord], list[str | None], int]


def _history(tmp_path: Path, sizes: list[int], cmds: list[str | None] | None = None) -> Hist:
    """One step per entry: a read/ls observation of `size` chars, or (cmd `edit write ...`) an
    edit with no observation. Returns turns, observations, obs id per entry, current step."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    rec = store.create_session("goal")
    observations: dict[str, ObservationRecord] = {}
    ids: list[str | None] = []
    for i, size in enumerate(sizes, start=1):
        cmd = (cmds[i - 1] if cmds and i <= len(cmds) else None) or f"bash ls dir{i}"
        store.add_turn(rec.id, step=i, role="assistant", content="", tool_cmd=cmd)
        if cmd.startswith("edit write"):
            store.add_turn(rec.id, step=i, role="tool", content="wrote a.py")
            ids.append(None)
            continue
        obs = store.add_observation(rec.id, step=i, cmd=cmd, raw_output="line\n" * (size // 5))
        observations[obs.id] = obs
        ids.append(obs.id)
        store.add_turn(rec.id, step=i, role="tool", content=obs.raw_output, obs_id=obs.id)
    return store.get_turns(rec.id), observations, ids, len(sizes) + 1


def _assemble(asm: ContextAssembler, hist: Hist) -> list[dict[str, Any]]:
    turns, observations, _, step = hist
    return asm.assemble(
        system_prompt="S",
        goal="goal",
        turns=turns,
        observations=observations,
        pins={},
        current_step=step,
    )


def _folded(msgs: list[dict[str, Any]]) -> list[str]:
    text = "\n".join(str(m["content"]) for m in msgs)
    return re.findall(r"\[(obs_\d+) folded", text)


def _used(hist: Hist) -> int:
    """The history estimate assemble() compares with the target (cap far above any obs)."""
    turns, observations, _, _ = hist
    asm = ContextAssembler(max_context_tokens=1 << 20)
    base = [{"role": "system", "content": "S"}, {"role": "user", "content": "Goal: goal"}]
    chars = sum(asm._turn_chars(t, observations) for t in turns)
    return estimate_messages_tokens(base, [ACT_TOOL_SCHEMA]) + chars // 4


def test_folds_only_as_needed_oldest_first(tmp_path: Path) -> None:
    # (a) under the target: nothing folds by age, even with many old observations
    small = _history(tmp_path / "a", [500] * 3 + [4000] * 6)
    assert (
        _folded(_assemble(ContextAssembler(auto_fold=True, max_context_tokens=32768), small)) == []
    )
    # (b) ~1500 tokens over the target; one 4000-char fold saves ~980 tokens, so two are needed
    hist = _history(tmp_path / "b", [4000] * 10)
    used = _used(hist)
    target = used - 1500
    asm = ContextAssembler(auto_fold=True, max_context_tokens=2 * target)
    folded = _folded(_assemble(asm, hist))
    ids = hist[2]
    assert folded == ids[:2]  # a contiguous oldest prefix, in order
    assert ids[2] not in folded and ids[8] not in folded  # old but not needed: stays
    obs = hist[1]
    saved = sum((obs[i].char_len - len(tombstone(obs[i]))) // 4 for i in folded)  # type: ignore[index]
    assert used - saved <= target
    assert asm.overflow == 0


def test_no_cliff_at_threshold(tmp_path: Path) -> None:
    hist = _history(tmp_path, [4000] * 9)  # K=2 at step 10: obs_1..obs_8 are old enough
    target = _used(hist) - 300  # over by less than one observation
    auto = ContextAssembler(auto_fold=True, max_context_tokens=2 * target)
    assert _folded(_assemble(auto, hist)) == [hist[2][0]]
    explicit = ContextAssembler(auto_fold=False, max_context_tokens=2 * target)
    assert _folded(_assemble(explicit, hist)) == hist[2][:8]  # today's cliff, explicit only


def test_newest_k_and_live_reads_protected(tmp_path: Path) -> None:
    # ~4800 of 8192 tokens: over the 4096 target even after every fold, under the 6144 budget.
    # ids[0] is a live read, ids[4] is newer than K; only ids[1..3] (age >= K) may fold.
    hist = _history(tmp_path, [8000, 300, 300, 300, 10000], ["edit view a.py"])
    asm = ContextAssembler(auto_fold=True, max_context_tokens=8192)
    msgs = _assemble(asm, hist)
    ids = hist[2]
    assert _folded(msgs) == ids[1:4]
    assert asm.overflow == 0  # the #81 budget stage had nothing to do
    text = "\n".join(str(m["content"]) for m in msgs)
    assert f"[{ids[0]}] line" in text and f"[{ids[4]}] line" in text


def test_mem_recall_never_age_folded(tmp_path: Path) -> None:
    hist = _history(tmp_path, [300, 300, 300, 8000, 8000], [None, "mem recall obs_9", None, None])
    msgs = _assemble(ContextAssembler(auto_fold=True, max_context_tokens=8192), hist)
    ids = hist[2]
    assert _folded(msgs) == [ids[0], ids[2], ids[3]]  # ids[1] skipped, ids[3] ends the run


def test_all_candidates_protected_folds_nothing(tmp_path: Path) -> None:
    # over the target, but the old ones are a live read or below fold_char_threshold
    hist = _history(tmp_path, [9000, 150, 150, 150, 9000], ["edit view a.py"])
    asm = ContextAssembler(auto_fold=True, max_context_tokens=8192)
    assert _folded(_assemble(asm, hist)) == []
    assert asm.overflow == 0


def test_tiny_window_only_budget_stage_differs_nothing(tmp_path: Path) -> None:
    hist = _history(tmp_path, [4000] * 3)
    auto = _assemble(ContextAssembler(auto_fold=True, max_context_tokens=1000), hist)
    explicit = _assemble(ContextAssembler(auto_fold=False, max_context_tokens=1000), hist)
    assert auto == explicit
    assert hist[2][2] in str(auto[-1]["content"])  # newest observation still shown (shrunk)


def test_explicit_fold_after_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hist = _history(tmp_path, [4000] * 9)
    ctx = 2 * (_used(hist) - 300)
    today = _assemble(ContextAssembler(fold_after_turns=2, max_context_tokens=ctx), hist)
    explicit = _assemble(ContextAssembler(auto_fold=False, max_context_tokens=ctx), hist)
    assert explicit == today
    assert _folded(today) == hist[2][:8]

    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    db = tmp_path / "h.db"
    h = Harness(model="decl/m", db_path=db)
    assert (h.auto_fold, h.fold_observations_after) == (True, 2)
    h = Harness(model="decl/m", db_path=db, fold_observations_after=2)
    assert (h.auto_fold, h.fold_observations_after) == (False, 2)
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        "decl:\n  kind: openai\n  base_url: http://x\n  api_key_env: K\n  fold_after: 4\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TETHER_PROVIDERS", str(yaml_path))
    h = Harness(model="decl/m", db_path=db)
    assert (h.auto_fold, h.fold_observations_after) == (False, 4)


async def test_harness_passes_auto_fold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TETHER_PROVIDERS", str(tmp_path / "none.yaml"))
    seen: list[bool] = []

    class Recording(ContextAssembler):
        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            seen.append(kw.get("auto_fold", False))

    monkeypatch.setattr(harness_mod, "ContextAssembler", Recording)
    ws = tmp_path / "ws"
    ws.mkdir()
    for flag, want in ((None, True), (3, False)):
        provider = FakeScriptedProvider(
            [ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"))]
        )
        h = Harness(
            db_path=tmp_path / "t.db",
            tools=["bash"],
            sandbox=SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False),
            provider=provider,
            fold_observations_after=flag,
        )
        await h.run("goal")
        assert seen[-1] is want


def test_reread_extends_window(tmp_path: Path) -> None:
    assert context.AUTO_FOLD_MAX_K == 8
    # (a) a.py read twice, unedited: K becomes 3, so the observation at age 2 is kept
    cmds: list[str | None] = ["cat a.py", "cat a.py", None, None, None]
    hist = _history(tmp_path / "a", [300, 300, 300, 9000, 9000], cmds)
    turns, observations, ids, _ = hist
    asm = ContextAssembler(auto_fold=True, max_context_tokens=8192)
    assert context.reread_count(turns, observations) == 1
    assert asm.effective_fold_after(turns, observations) == 3
    folded = _folded(_assemble(asm, hist))
    assert ids[0] in folded and ids[3] not in folded
    # explicit K never extends
    assert ContextAssembler(fold_after_turns=2).effective_fold_after(turns, observations) == 2

    # (b) an edit between the reads: not a re-read, the observation at age 2 folds
    cmds = ["cat a.py", "edit write a.py", "cat a.py", None, None, None]
    hist = _history(tmp_path / "b", [300, 0, 300, 300, 9000, 9000], cmds)
    turns, observations, ids, _ = hist
    asm = ContextAssembler(auto_fold=True, max_context_tokens=8192)
    assert context.reread_count(turns, observations) == 0
    assert asm.effective_fold_after(turns, observations) == 2
    assert ids[4] in _folded(_assemble(asm, hist))

    # (c) bounded: 20 reads (19 re-reads) cap K at AUTO_FOLD_MAX_K
    hist = _history(tmp_path / "c", [300] * 20, ["cat a.py"] * 20)
    turns, observations, _, _ = hist
    assert context.reread_count(turns, observations) == 19
    asm = ContextAssembler(auto_fold=True)
    assert asm.effective_fold_after(turns, observations) == 8


def test_reread_ignores_other_ranges_and_pointers(tmp_path: Path) -> None:
    cmds: list[str | None] = ["edit view a.py --lines 1:10", "edit view a.py --lines 20:30"]
    turns, observations, _, _ = _history(tmp_path / "a", [300, 300], cmds)
    assert context.reread_count(turns, observations) == 0
    # a #199 pointer answers a repeated read without an observation: not a re-read
    store = SQLiteStore(db_path=tmp_path / "p.db")
    rec = store.create_session("goal")
    obs = store.add_observation(rec.id, step=1, cmd="cat a.py", raw_output="x" * 300)
    store.add_turn(rec.id, step=1, role="assistant", content="", tool_cmd="cat a.py")
    store.add_turn(rec.id, step=1, role="tool", content=obs.raw_output, obs_id=obs.id)
    store.add_turn(rec.id, step=2, role="assistant", content="", tool_cmd="cat a.py")
    store.add_turn(rec.id, step=2, role="tool", content=f"[{obs.id} unchanged] already read")
    assert context.reread_count(store.get_turns(rec.id), {obs.id: obs}) == 0
    assert context.reread_count([], {}) == 0  # empty history
