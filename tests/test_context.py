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
