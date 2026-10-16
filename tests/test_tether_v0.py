"""Comprehensive unit, security, RAG, and token-budget tests for Tether v0."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

import pytest

from tether import Harness, SandboxPolicy, SandboxViolationError, SkillLoader, tool
from tether.context import (
    ACT_TOOL_SCHEMA,
    ContextAssembler,
    estimate_messages_tokens,
    estimate_tokens,
)
from tether.providers.base import ActionCall, ModelResponse, extract_fallback_action


class FakeScriptedProvider:
    """Deterministic scripted provider for testing the Harness loop."""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.model_name = "fake/qwen3.5:9b"
        self._responses = list(responses)
        self.recorded_calls: list[list[dict[str, Any]]] = []

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        self.recorded_calls.append(list(messages))
        if not self._responses:
            return ModelResponse(
                content="Finishing up",
                action=ActionCall(cmd="done", stdin="Default completion"),
            )
        return self._responses.pop(0)


def test_token_budgets_and_zero_default_tools(tmp_path: Path) -> None:
    """Golden Rules 1, 2, 4: Base framing < 150 tokens, zero optional tools by default."""
    harness = Harness(db_path=tmp_path / "tether.db")
    mux = harness.build_multiplexer(
        session_id="ses_test",
        enabled_tools=[],
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model="ollama/qwen3.5:9b",
    )
    # Only `done` loaded by default
    assert mux.tool_names == ["done"]

    assembler = ContextAssembler()
    sys_prompt = assembler.build_system_prompt(mux.toolbox_index())
    total_base_tokens = estimate_messages_tokens(
        [{"role": "system", "content": sys_prompt}],
        [ACT_TOOL_SCHEMA],
    )
    assert total_base_tokens < 150, f"Base framing exceeded 150 tokens: {total_base_tokens}"

    # Check all built-in tools obey <= 12 tokens for index line and <= 60 tokens for --help
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


async def test_custom_tool_introspection_and_9b_quirks(tmp_path: Path) -> None:
    """Test @tool CLI parsing, stdin payloads, 9B quirk normalization, and JIT --help on errors."""

    @tool(name="crm", description="Update customer subscription tier")
    def update_tier(
        customer_id: int,
        tier: Literal["free", "pro", "enterprise"] = "pro",
        stdin: str | None = None,
    ) -> str:
        """Update customer tier with optional audit note via stdin."""
        return f"customer={customer_id} tier={tier} note={stdin or 'none'}"

    harness = Harness(db_path=tmp_path / "tether.db", tools=[update_tier])
    mux = harness.build_multiplexer(
        session_id="ses_1",
        enabled_tools=["crm"],
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model="ollama/qwen3.5:9b",
    )

    # 1. Progressive --help
    help_res = await mux.execute("crm --help")
    assert "Usage: crm <customer_id:int>" in help_res.output
    assert "free|pro|enterprise" in help_res.output

    # 2. Self-healing error on invalid argument type (no unhandled exception)
    err_res = await mux.execute("crm not_an_int")
    assert err_res.is_error
    assert "expects int" in err_res.output
    assert "Usage: crm" in err_res.output

    # 3. 9B quirk normalization (`$ ` prefix, backticks, flags + stdin)
    ok_res = await mux.execute("`$ crm 1042 --tier enterprise`", stdin="Approved by finance")
    assert not ok_res.is_error
    assert ok_res.output == "customer=1042 tier=enterprise note=Approved by finance"


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
            # Step 1: 9B model thinks out loud without calling `act` -> harness nudges it
            ModelResponse(content="Let me check the internal docs first.", action=None),
            # Step 2: Model fetches docs (obs_1)
            ModelResponse(content="", action=ActionCall(cmd="docs rate-limits")),
            # Step 3: Model pins a fact (obs_2)
            ModelResponse(content="", action=ActionCall(cmd="mem pin status active")),
            # Step 4: By step 4, obs_1 (from step 2) is folded! Model searches it with BM25 RAG
            ModelResponse(
                content="", action=ActionCall(cmd='mem search "enterprise requests minute"')
            ),
            # Step 5: Model finishes explicitly with `done`
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

    # Verify KV-cache static system prompt immutability across all 5 turns
    first_sys = provider.recorded_calls[0][0]["content"]
    for call_msgs in provider.recorded_calls:
        assert call_msgs[0]["content"] == first_sys

    # Verify that on step 4 (index 3), obs_1 was folded into a 1-line tombstone
    step4_prompt = "\n".join(m["content"] for m in provider.recorded_calls[3])
    assert "[obs_1 folded:" in step4_prompt
    assert "Legacy REST v1 endpoints" not in step4_prompt

    # Verify that `mem search` in step 4 returned the exact rate-limit chunk for step 5
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
            # Step 1: Spawn async sub-agent
            ModelResponse(
                content="",
                action=ActionCall(cmd='agent spawn "Benchmark Qwen3.5 9B"'),
            ),
            # Step 2: Wait for all child sessions and inspect compact digest
            ModelResponse(
                content="",
                action=ActionCall(cmd='agent query --all "tokens/sec RTX 4090" --top 1'),
            ),
            # Step 3: Complete
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
    # Let's run parent; between step 1 and step 2 the child task completes
    rec = harness.create_session("Coordinate benchmark research")
    # Execute step-by-step via execute_session; give child task a tiny yield via wait or sleep
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

    # Check that the BM25 RAG query retrieved only the throughput section
    step3_prompt = "\n".join(m["content"] for m in parent_provider.recorded_calls[2])
    assert "118 tokens/sec" in step3_prompt
    # Verify compact digest stays well under 80 tokens
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
    # Verify the resumed turn had both the follow-up instruction and the pinned memory
    last_call_text = "\n".join(m["content"] for m in provider.recorded_calls[-1])
    assert "Now complete phase 2" in last_call_text
    assert "project: tether" in last_call_text


async def test_deterministic_security_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 6: Verify workspace path jail, sensitive file block, and env scrubbing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-key-12345")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-999")

    sandbox = SandboxPolicy(
        profile="workspace-write",
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
    )

    # 1. Path traversal outside workspace is deterministically blocked
    with pytest.raises(SandboxViolationError, match="outside workspace"):
        sandbox.resolve_safe_path("../outside.txt", write=True)

    # 2. Protected files (.env, .git/config, .tether) are deterministically blocked
    for forbidden in (
        ".env",
        ".env.local",
        ".git/config",
        ".git/hooks/pre-commit",
        ".tether/tether.db",
    ):
        with pytest.raises(SandboxViolationError, match="protected path"):
            sandbox.resolve_safe_path(forbidden, write=False)

    # 3. Dangerous shell commands are deterministically blocked
    for bad_cmd in ("sudo ls", "rm -rf /", "cat .env", "ls ../", "chmod 777 file.txt"):
        with pytest.raises(SandboxViolationError):
            await sandbox.execute_bash(bad_cmd)

    # 4. Secret environment variables are scrubbed from bash subprocesses
    env_out = await sandbox.execute_bash("env")
    assert "sk-super-secret-key-12345" not in env_out
    assert "aws-secret-999" not in env_out

    # 5. Privilege attenuation: read-only parent can never spawn workspace-write child
    ro_parent = SandboxPolicy(profile="read-only", workspace_root=tmp_path)
    child_policy = ro_parent.attenuate("workspace-write")
    assert child_policy.profile == "read-only"
    with pytest.raises(SandboxViolationError, match="read-only"):
        child_policy.resolve_safe_path("notes.txt", write=True)


async def test_edit_tool_and_skill_loader(tmp_path: Path) -> None:
    """Verify workspace-jailed `edit` tool and SkillLoader with sibling tools.py."""
    skill_dir = tmp_path / "skills" / "analyst"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: analyst\n"
        "description: Financial ratio calculator\n"
        "model: ollama/qwen3.5:9b\n"
        "tools: [edit, calc-margin]\n"
        "---\n"
        "Use calc-margin and write results.",
        encoding="utf-8",
    )
    (skill_dir / "tools.py").write_text(
        "from tether import tool\n\n"
        "@tool(name='calc-margin', description='Compute profit margin percentage')\n"
        "def calc_margin(revenue: float, cost: float) -> str:\n"
        "    return f'{((revenue - cost) / revenue) * 100:.1f}%'\n",
        encoding="utf-8",
    )

    loader = SkillLoader(search_dirs=[tmp_path / "skills"])
    sk = loader.load("analyst")
    assert sk is not None
    assert sk.model == "ollama/qwen3.5:9b"
    assert len(sk.custom_tools) == 1

    harness = Harness(
        db_path=tmp_path / "tether.db",
        skill=sk,
        sandbox=SandboxPolicy(workspace_root=tmp_path),
    )
    mux = harness.build_multiplexer(
        session_id="ses_skill",
        enabled_tools=sk.tools,
        sandbox=SandboxPolicy(workspace_root=tmp_path),
        model=sk.model,
    )

    res_calc = await mux.execute("calc-margin 200 50")
    assert res_calc.output == "75.0%"

    res_write = await mux.execute("edit write report.txt", stdin="line 1\nline 2\nline 3\n")
    assert "Wrote" in res_write.output

    res_rep = await mux.execute("edit replace report.txt --lines 2:2", stdin="updated line 2")
    assert "Replaced lines 2:2" in res_rep.output

    res_view = await mux.execute("edit view report.txt --lines 1:3")
    assert "updated line 2" in res_view.output


def test_fallback_9b_action_extractor() -> None:
    """Verify fallback extraction for Qwen <tool_call> XML and inline act(...) syntax."""
    xml_text = (
        "I will search now.\n"
        "<tool_call>\n"
        '{"name": "act", "arguments": {"cmd": "web search \\"AI news\\""}}\n'
        "</tool_call>"
    )
    call1 = extract_fallback_action(xml_text)
    assert call1 is not None
    assert call1.cmd == 'web search "AI news"'

    py_text = 'Thought: finished.\nact("done", stdin="Final report ready")'
    call2 = extract_fallback_action(py_text)
    assert call2 is not None
    assert call2.cmd == "done"
    assert call2.stdin == "Final report ready"
