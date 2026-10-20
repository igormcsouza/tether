"""Unit tests for tether/context.py (L1 elision, folding, KV-cache prefix, token budgets)."""

from __future__ import annotations

from pathlib import Path

from tether import Harness, SandboxPolicy
from tether.context import (
    ACT_TOOL_SCHEMA,
    ContextAssembler,
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


def _fold_setup(tmp_path: Path, cmds: list[str], outputs: list[str]):  # type: ignore[no-untyped-def]
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    rec = store.create_session("goal")
    observations = {}
    for i, (cmd, out) in enumerate(zip(cmds, outputs, strict=True), start=1):
        step = i
        if cmd.startswith("edit write") or cmd.startswith("edit replace"):
            store.add_turn(rec.id, step=step, role="assistant", content="", tool_cmd=cmd)
            store.add_turn(rec.id, step=step, role="tool", content=out)
            continue
        obs = store.add_observation(rec.id, step=step, cmd=cmd, raw_output=out)
        observations[obs.id] = obs
        store.add_turn(rec.id, step=step, role="assistant", content="", tool_cmd=cmd)
        store.add_turn(rec.id, step=step, role="tool", content=out, obs_id=obs.id)
    return store, rec, observations


def _render(store, rec, observations, step: int, **kw) -> str:  # type: ignore[no-untyped-def]
    msgs = ContextAssembler(fold_after_turns=2, **kw).assemble(
        system_prompt="S",
        goal=rec.goal,
        turns=store.get_turns(rec.id),
        observations=observations,
        pins={},
        current_step=step,
    )
    return "\n".join(str(m["content"]) for m in msgs)


def test_unedited_file_read_is_not_folded(tmp_path: Path) -> None:
    body = "line\n" * 100
    for cmd in ("edit view a.py", "bash sed -n '1,55p' a.py", "bash cat a.py"):
        store, rec, obs = _fold_setup(tmp_path / cmd.split()[1], [cmd, "bash ls"], [body, body])
        text = _render(store, rec, obs, step=20)
        assert "obs_1 folded" not in text and "[obs_1] line" in text
        assert "obs_2 folded" in text  # non-read output still folds


def test_read_folds_after_edit_or_reread(tmp_path: Path) -> None:
    body = "line\n" * 100
    store, rec, obs = _fold_setup(
        tmp_path / "e",
        ["edit view a.py", "edit replace a.py", "edit view b.py"],
        [body, "ok", body],
    )
    text = _render(store, rec, obs, step=20)
    assert "obs_1 folded" in text  # edited since: folds
    assert "[obs_2] line" in text  # other path untouched

    store, rec, obs = _fold_setup(
        tmp_path / "r", ["edit view a.py", "edit view a.py"], [body, body]
    )
    text = _render(store, rec, obs, step=20)
    assert "obs_1 folded" in text and "[obs_2] line" in text  # superseded by same re-read


def test_read_path_ignores_non_reads() -> None:
    from tether.context import _read_path

    assert _read_path("bash cat a.py | head") is None
    assert _read_path("bash grep x a.py") is None
    assert _read_path("bash cat -n") is None
    assert _read_path("bash cat 'unclosed") is None
    assert _read_path("edit view") is None


def test_tombstone_hint_follows_mem_availability(tmp_path: Path) -> None:
    big = "x" * 5000
    store, rec, obs = _fold_setup(tmp_path, ["bash ls", "bash pwd"], [big, big])
    with_mem = _render(store, rec, obs, step=20)
    assert "mem recall obs_1" in with_mem
    no_mem = _render(store, rec, obs, step=20, mem_enabled=False)
    assert "mem recall" not in no_mem and "re-run the command if needed]" in no_mem
    # active (not yet folded) head+tail elision marker follows the same rule
    active = _render(store, rec, obs, step=2, mem_enabled=False)
    assert "mem recall" not in active and "re-run the command for the full output" in active
