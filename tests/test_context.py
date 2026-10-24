"""Unit tests for tether/context.py (L1 elision, folding, KV-cache prefix, token budgets)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tether import Harness, SandboxPolicy
from tether.context import (
    ACT_TOOL_SCHEMA,
    MAX_LIVE_READS,
    ContextAssembler,
    _read_path,
    elide_active_observation,
    estimate_messages_tokens,
    estimate_tokens,
)
from tether.store import SQLiteStore, TurnRecord


def test_token_budgets_and_zero_default_tools(tmp_path: Path) -> None:
    """Golden Rules 1, 2, 4: Base framing < 150 tokens, zero optional tools by default."""
    harness = Harness(db_path=tmp_path / "tether.db")
    mux = harness.build_multiplexer(
        session_id="ses_test",
        enabled_tools=[],
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model="ollama/qwen3.5:9b",
    )
    assert mux.tool_names == ["done"]

    assembler = ContextAssembler()
    sys_prompt = assembler.build_system_prompt(mux.toolbox_index())
    total_base_tokens = estimate_messages_tokens(
        [{"role": "system", "content": sys_prompt}],
        [ACT_TOOL_SCHEMA],
    )
    assert total_base_tokens < 150, f"Base framing exceeded 150 tokens: {total_base_tokens}"

    full_mux = harness.build_multiplexer(
        session_id="ses_test",
        enabled_tools=["all"],
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model="ollama/qwen3.5:9b",
    )
    for name in full_mux.tool_names:
        spec = full_mux.get_tool(name)
        assert spec is not None
        idx_tokens = estimate_tokens(spec.index_line())
        help_tokens = estimate_tokens(spec.help_text())
        assert idx_tokens <= 12, f"{name} index line too long: {idx_tokens} tokens"
        assert help_tokens <= 60, f"{name} --help too long: {help_tokens} tokens"


def test_head_tail_active_observation_elision(tmp_path: Path) -> None:
    """Verify oversized active observations keep Head + Tail in L1."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    rec = store.create_session("Test head tail elision")
    big_text = "HEAD_MARKER_" + ("middle_noise " * 400) + "_TAIL_TRACEBACK_EXIT_0"
    obs = store.add_observation(rec.id, step=1, cmd="bash run.sh", raw_output=big_text)
    store.add_turn(rec.id, step=1, role="tool", content=obs.raw_output, obs_id=obs.id)

    elided = elide_active_observation(obs.id, big_text, max_chars=400)
    assert "HEAD_MARKER_" in elided
    assert "_TAIL_TRACEBACK_EXIT_0" in elided
    assert "middle chars elided in L1" in elided
    assert len(elided) < 600

    assembler = ContextAssembler(fold_after_turns=2, active_char_cap=400)
    msgs = assembler.assemble(
        system_prompt="Sys",
        goal=rec.goal,
        turns=store.get_turns(rec.id),
        observations=store.list_observations(rec.id),
        pins={},
        current_step=2,
    )
    obs_msg = msgs[-1]["content"]
    assert "HEAD_MARKER_" in obs_msg
    assert "_TAIL_TRACEBACK_EXIT_0" in obs_msg
    assert "middle chars elided in L1" in obs_msg


def test_kv_prefix_immutability_with_pins(tmp_path: Path) -> None:
    """Verify earlier turn messages stay byte-identical when new turns are added after pins."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    rec = store.create_session("Test prefix stability")
    store.set_pin(rec.id, "key1", "val1")

    store.add_turn(rec.id, step=1, role="assistant", content="", tool_cmd="mem pin key1 val1")
    store.add_turn(rec.id, step=1, role="tool", content="Pinned key1")

    assembler = ContextAssembler(fold_after_turns=5)
    msgs_step2 = assembler.assemble(
        system_prompt="StaticSys",
        goal=rec.goal,
        turns=store.get_turns(rec.id),
        observations={},
        pins=store.get_pins(rec.id),
        current_step=2,
    )

    store.add_turn(rec.id, step=2, role="assistant", content="", tool_cmd="web search test")
    store.add_turn(rec.id, step=2, role="tool", content="Search results")

    msgs_step3 = assembler.assemble(
        system_prompt="StaticSys",
        goal=rec.goal,
        turns=store.get_turns(rec.id),
        observations={},
        pins=store.get_pins(rec.id),
        current_step=3,
    )
    assert len(msgs_step2) == 4
    assert len(msgs_step3) == 6
    assert msgs_step2[:3] == msgs_step3[:3]
    assert "[PINNED MEMORY]" in msgs_step3[-1]["content"]
    assert "[PINNED MEMORY]" not in msgs_step3[3]["content"]

    # Project-scoped pins (__project__) must never mutate static system prompt or session L1 pins
    sys_before = assembler.build_system_prompt("- mem: memory")
    store.set_pin("__project__", "global_convention", "Use strict mypy")
    sys_after = assembler.build_system_prompt("- mem: memory")
    assert sys_before == sys_after
    assert "global_convention" not in str(store.get_pins(rec.id))


def test_context_assembler_edge_cases() -> None:
    """Cover token estimation, static system prompt caching, and window trimming with pins."""
    assert estimate_tokens("") == 0
    msgs = [{"role": "assistant", "content": "hi", "tool_calls": [{"name": "act"}]}]
    assert estimate_messages_tokens(msgs) > 4

    ca = ContextAssembler(max_context_tokens=50)
    p1 = ca.build_system_prompt("- done: finish", skill_instructions="Be concise.")
    p2 = ca.build_system_prompt("- done: finish")
    assert p1 == p2 and "[SKILL]" in p1

    turns = [
        TurnRecord(1, "s", 1, "user", "long text " * 30, None, None, None, 0.0),
        TurnRecord(2, "s", 1, "assistant", "resp", "web search", "stdin_payload", None, 0.0),
        TurnRecord(3, "s", 2, "user", "more text " * 30, None, None, None, 0.0),
        TurnRecord(4, "s", 2, "assistant", "thinking", None, None, None, 0.0),
    ]
    assembled = ca.assemble(
        system_prompt="Sys",
        goal="Goal",
        turns=turns,
        observations={},
        pins={"k": "v"},
        current_step=3,
    )
    assert "[PINNED MEMORY]" in assembled[-1]["content"]


def _text(tmp_path: Path, cmds: list[str], step: int = 20, **kw: Any) -> str:
    """Render history where each cmd produced a 500-char observation (obs_1, obs_2, ...)."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    rec = store.create_session("goal")
    observations = {}
    for i, cmd in enumerate(cmds, start=1):
        obs = store.add_observation(rec.id, step=i, cmd=cmd, raw_output="line\n" * 100)
        observations[obs.id] = obs
        store.add_turn(rec.id, step=i, role="assistant", content="", tool_cmd=cmd)
        store.add_turn(rec.id, step=i, role="tool", content=obs.raw_output, obs_id=obs.id)
    msgs = ContextAssembler(fold_after_turns=2, **kw).assemble(
        system_prompt="S",
        goal=rec.goal,
        turns=store.get_turns(rec.id),
        observations=observations,
        pins={},
        current_step=step,
    )
    return "\n".join(str(m["content"]) for m in msgs)


def _live(text: str, n: int) -> bool:
    return f"[obs_{n}] line" in text and f"obs_{n} folded" not in text


def test_unedited_file_read_is_not_folded(tmp_path: Path) -> None:
    for i, cmd in enumerate(("edit view a.py", "bash sed -n '1,55p' a.py", "bash cat a.py")):
        text = _text(tmp_path / str(i), [cmd, "bash ls"])
        assert _live(text, 1)
        assert "obs_2 folded" in text  # non-read output still folds


def test_edit_or_reread_folds_old_read(tmp_path: Path) -> None:
    text = _text(tmp_path / "e", ["edit view a.py", "edit replace a.py", "edit view b.py"])
    assert "obs_1 folded" in text and _live(text, 3)
    text = _text(tmp_path / "r", ["edit view a.py", "bash cat a.py"])  # same file, latest wins
    assert "obs_1 folded" in text and _live(text, 2)


def test_bash_write_invalidates_live_read(tmp_path: Path) -> None:
    for i, cmd in enumerate(
        (
            "bash sed -i 's/a/b/' a.py",
            "bash tee a.py",
            "bash echo x > a.py",
            "bash python -c 'a.py'",
        )
    ):
        text = _text(tmp_path / str(i), ["edit view a.py", cmd, "edit view b.py"])
        assert "obs_1 folded" in text, cmd
        assert _live(text, 3)
    # a bash command not mentioning the path leaves it live
    assert _live(_text(tmp_path / "x", ["edit view a.py", "bash ls"]), 1)


def test_paths_are_normalized(tmp_path: Path) -> None:
    root = str(tmp_path)
    text = _text(
        tmp_path / "n", ["edit view ./a.py", f"edit view {root}/a.py"], workspace_root=root
    )
    assert "obs_1 folded" in text and _live(text, 2)
    text = _text(
        tmp_path / "w", ["edit view a.py", f"edit replace {root}/a.py"], workspace_root=root
    )
    assert "obs_1 folded" in text


def test_live_reads_are_capped(tmp_path: Path) -> None:
    text = _text(tmp_path, [f"edit view f{i}.py" for i in range(MAX_LIVE_READS + 1)])
    assert "obs_1 folded" in text
    assert all(_live(text, n) for n in range(2, MAX_LIVE_READS + 2))


def test_read_path_ignores_non_reads() -> None:
    assert _read_path("bash cat a.py | head") is None
    assert _read_path("bash grep x a.py") is None
    assert _read_path("bash sed -i s/a/b/ a.py") is None
    assert _read_path("bash sed -n -i s/a/b/ a.py") is None
    assert _read_path("bash sed s/a/b/ a.py") is None
    assert _read_path("bash cat -n") is None
    assert _read_path("bash cat 'unclosed") is None
    assert _read_path("edit view") is None


def test_tombstone_hint_follows_mem_availability(tmp_path: Path) -> None:
    cmds = ["bash ls", "bash pwd"]
    assert "mem recall obs_1" in _text(tmp_path / "a", cmds)
    no_mem = _text(tmp_path / "b", cmds, mem_enabled=False)
    assert "mem recall" not in no_mem and "re-run the command if needed]" in no_mem
    # active (not yet folded) head+tail elision marker follows the same rule
    store = SQLiteStore(db_path=tmp_path / "c.db")
    rec = store.create_session("g")
    obs = store.add_observation(rec.id, step=1, cmd="bash ls", raw_output="x" * 20000)
    store.add_turn(rec.id, step=1, role="tool", content="", obs_id=obs.id)
    msgs = ContextAssembler(mem_enabled=False).assemble(
        system_prompt="S",
        goal="g",
        turns=store.get_turns(rec.id),
        observations={obs.id: obs},
        pins={},
        current_step=1,
    )
    flat = str(msgs)
    assert "mem recall" not in flat and "re-run the command for the full output" in flat


def test_ranges_of_one_file_stay_live_together(tmp_path: Path) -> None:
    text = _text(tmp_path, ["edit view a.py --lines 1:5", "edit view a.py --lines 6:9"])
    assert _live(text, 1) and _live(text, 2)
    text = _text(tmp_path / "r", ["edit view a.py --lines 1:5", "edit view a.py --lines 1:5"])
    assert "obs_1 folded" in text and _live(text, 2)


def _budget_run(n_obs: int, size: int, budget: int, **kw: Any) -> tuple[ContextAssembler, list]:
    from tether.store import ObservationRecord

    turns: list[TurnRecord] = []
    obs: dict[str, ObservationRecord] = {}
    for i in range(1, n_obs + 1):
        o = ObservationRecord(f"obs_{i}", "s", i, f"bash echo {i}", f"{i}" * size, "", size)
        obs[o.id] = o
        turns.append(TurnRecord(2 * i, "s", i, "assistant", "", f"bash echo {i}", None, None, 0.0))
        turns.append(TurnRecord(2 * i + 1, "s", i, "tool", "x", None, None, o.id, 0.0))
    ca = ContextAssembler(max_context_tokens=budget, structured=True, **kw)
    msgs = ca.assemble(
        system_prompt="Sys", goal="Goal", turns=turns, observations=obs, pins={}, current_step=n_obs
    )
    return ca, msgs


def test_budget_folds_live_observations_before_dropping_history() -> None:
    # 8 live observations (fold window 8) of ~600 tokens each, budget 2,000: fold, do not drop
    ca, msgs = _budget_run(8, 2400, 2000, fold_after_turns=8)
    assert estimate_messages_tokens(msgs, [ACT_TOOL_SCHEMA]) <= 2000 and ca.overflow == 0
    text = "\n".join(str(m.get("content")) for m in msgs)
    assert "[obs_1 folded" in text and "[obs_8] 8888" in text  # old folded, newest intact
    assert sum(1 for m in msgs if m["role"] == "tool") == 8  # nothing dropped


def test_budget_shrinks_the_newest_observation_as_a_last_resort() -> None:
    ca, msgs = _budget_run(1, 9000, 700)
    assert ca.overflow == 0
    assert estimate_messages_tokens(msgs, [ACT_TOOL_SCHEMA]) <= 700
    assert "elided" in str(msgs[-1]["content"])


def test_budget_overflow_is_reported_when_nothing_fits() -> None:
    ca, _ = _budget_run(1, 100, 10)  # system + goal + schema alone exceed 10 tokens
    assert ca.overflow > 0


def test_calibration_tightens_the_budget_and_never_loosens_it() -> None:
    ca = ContextAssembler()
    ca.calibrate(1000, 1250)
    assert ca.calibration == 1.25
    ca.calibrate(1000, 400)  # cached-prefix counts must not widen the budget
    assert ca.calibration == 1.0
    ca.calibrate(1000, 9000)
    assert ca.calibration == 1.5
    ca.calibrate(0, 5)
    assert ca.calibration == 1.5


def test_mem_recall_results_are_not_folded_again(tmp_path: Path) -> None:
    # Folding a recall's own output sent GLM-5.3 on a 10-step `mem recall obs_N` chain (#86).
    text = _text(tmp_path, ["bash ls", "mem recall obs_1", "bash echo a", "bash echo b"])
    assert _live(text, 2) and "obs_1 folded" in text and "obs_3 folded" in text


def test_active_observation_cap_follows_the_context_budget(tmp_path: Path) -> None:
    """A 9 KB test file is shown whole on the default budget, head+tail on a tiny one."""
    store = SQLiteStore(db_path=tmp_path / "c.db")
    rec = store.create_session("g")
    obs = store.add_observation(rec.id, step=1, cmd="bash cat t.py", raw_output="x" * 9000)
    store.add_turn(rec.id, step=1, role="tool", content="", obs_id=obs.id)

    def shown(**kw: int) -> str:
        msgs = ContextAssembler(**kw).assemble(
            system_prompt="S",
            goal="g",
            turns=store.get_turns(rec.id),
            observations={obs.id: obs},
            pins={},
            current_step=1,
        )
        return str(msgs)

    assert "elided" not in shown()
    assert "elided" in shown(max_context_tokens=2048)
    assert ContextAssembler(max_context_tokens=100).active_char_cap == 2400


def test_budget_reserves_an_eighth_of_the_window_for_the_reply() -> None:
    # #144: a prompt that fills the window cuts off the model's file writes
    ca, msgs = _budget_run(8, 2400, 2000, fold_after_turns=8)
    assert estimate_messages_tokens(msgs, [ACT_TOOL_SCHEMA]) <= 2000 * 7 // 8
