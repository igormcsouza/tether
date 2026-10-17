"""End-to-end integration tests for Tether (RAG observation folding, sub-agents, live inbox)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, tool
from tether.context import estimate_tokens


async def test_explicit_done_and_ephemeral_folding_with_rag(tmp_path: Path) -> None:
    """Verify plain-text nudge, KV-cache prefix stability, folding, and `mem search` RAG."""
    large_article = (
        "# Alpha Release Notes\n"
        "The Alpha module introduces zero-copy tensor streaming for edge GPUs.\n\n"
        "# Rate Limits & Quotas\n"
        "The enterprise tier supports 12,500 requests per minute with burst capacity.\n\n"
        "# Deprecation Notice\n"
        "Legacy REST v1 endpoints will be retired in December."
    )

    @tool(name="docs", description="Fetch internal documentation")
    def fetch_docs(topic: str) -> str:
        return large_article

    provider = FakeScriptedProvider(
        [
            ModelResponse(content="Let me check the internal docs first.", action=None),
            ModelResponse(content="", action=ActionCall(cmd="docs rate-limits")),
            ModelResponse(content="", action=ActionCall(cmd="mem pin status active")),
            ModelResponse(
                content="", action=ActionCall(cmd='mem search "enterprise requests minute"')
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="done", stdin="Enterprise allows 12,500 req/min."),
            ),
        ]
    )

    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=["mem", fetch_docs],
        fold_observations_after=2,
        provider=provider,
    )
    session = await harness.run("What is the enterprise rate limit?")
    assert session.status == "COMPLETED"
    assert session.result == "Enterprise allows 12,500 req/min."
    assert session.step_count == 5

    first_sys = provider.recorded_calls[0][0]["content"]
    for call_msgs in provider.recorded_calls:
        assert call_msgs[0]["content"] == first_sys

    step4_prompt = "\n".join(m["content"] for m in provider.recorded_calls[3])
    assert "[obs_1 folded:" in step4_prompt
    assert "Legacy REST v1 endpoints" not in step4_prompt

    step5_prompt = "\n".join(m["content"] for m in provider.recorded_calls[4])
    assert "12,500 requests per minute" in step5_prompt


async def test_async_subagents_and_sqlite_fts5_rag(tmp_path: Path) -> None:
    """Test `agent spawn`, compact `agent wait` digest, and `agent query` BM25 RAG."""
    db_file = tmp_path / "tether.db"

    def in_process_spawner(child_session_id: str) -> int | None:
        child_provider = FakeScriptedProvider(
            [
                ModelResponse(
                    content="",
                    action=ActionCall(
                        cmd="done",
                        stdin=(
                            "# Executive Overview\n"
                            "We benchmarked three local inference engines.\n\n"
                            "# Qwen3.5 9B Throughput\n"
                            "On an RTX 4090, Qwen3.5:9b achieved 118 tokens/sec "
                            "with KV prefix caching.\n\n"
                            "# Memory Footprint\n"
                            "Quantized Q4_K_M weights require 6.1 GB of VRAM."
                        ),
                    ),
                )
            ]
        )
        child_harness = Harness(db_path=db_file, provider=child_provider)
        asyncio.get_running_loop().create_task(child_harness.execute_session(child_session_id))
        return 9999

    parent_provider = FakeScriptedProvider(
        [
            ModelResponse(
                content="",
                action=ActionCall(cmd='agent spawn "Benchmark Qwen3.5 9B"'),
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd='agent query --all "tokens/sec RTX 4090" --top 1'),
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="done", stdin="Qwen3.5:9b hits 118 tokens/sec on RTX 4090."),
            ),
        ]
    )

    harness = Harness(
        db_path=db_file,
        tools=["agent"],
        provider=parent_provider,
        worker_spawner=in_process_spawner,
    )
    rec = harness.create_session("Coordinate benchmark research")
    orig_generate = parent_provider.generate

    async def _delayed_generate(
        messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse:
        await asyncio.sleep(0.05)
        return await orig_generate(messages, tools)

    parent_provider.generate = _delayed_generate  # type: ignore[method-assign]
    final_rec = await harness.execute_session(rec.id)

    assert final_rec.status == "COMPLETED"
    assert "118 tokens/sec" in (final_rec.result or "")

    step3_prompt = "\n".join(m["content"] for m in parent_provider.recorded_calls[2])
    assert "118 tokens/sec" in step3_prompt
    children = harness.store.list_sessions(parent_id=rec.id)
    assert len(children) == 1
    digest = harness.store.get_session_digest(children[0].id)
    assert estimate_tokens(digest) < 80
    assert "COMPLETED" in digest


async def test_live_inbox_and_auto_resume(tmp_path: Path) -> None:
    """Test sending a follow-up instruction to a COMPLETED session resumes it from SQLite."""
    db_file = tmp_path / "tether.db"
    provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd="mem pin project tether")),
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Initial phase done.")),
            ModelResponse(
                content="",
                action=ActionCall(
                    cmd="done", stdin="Resumed phase complete with pinned project=tether."
                ),
            ),
        ]
    )
    harness = Harness(db_path=db_file, tools=["mem"], provider=provider)
    first = await harness.run("Start phase 1")
    assert first.status == "COMPLETED"
    assert first.result == "Initial phase done."

    resumed = await harness.send(first.id, "Now complete phase 2")
    assert resumed.status == "COMPLETED"
    assert resumed.result == "Resumed phase complete with pinned project=tether."
    last_call_text = "\n".join(m["content"] for m in provider.recorded_calls[-1])
    assert "Now complete phase 2" in last_call_text
    assert "project: tether" in last_call_text
