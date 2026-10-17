"""Unit tests for tether/harness.py (agent loop, loop-stall breaker, worker spawn, recovery)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, register_provider, tool
from tether.decorator import ToolSpec
from tether.harness import spawn_detached_worker
from tether.store import SQLiteStore


async def test_deterministic_loop_stall_breaker(tmp_path: Path) -> None:
    """Verify consecutive identical commands trigger a deterministic [LOOP DETECTED] nudge."""
    call_count = 0

    @tool(name="ping", description="Ping a host")
    def ping(host: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"pong from {host}"

    provider = FakeScriptedProvider(
        [
            ModelResponse(
                content="",
                action=ActionCall(cmd="ping"),
                prompt_tokens=100,
                completion_tokens=20,
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="edit view missing_file_xyz.txt"),
                prompt_tokens=110,
                completion_tokens=20,
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="ping example.com"),
                prompt_tokens=120,
                completion_tokens=25,
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="ping example.com"),
                prompt_tokens=130,
                completion_tokens=25,
            ),
            ModelResponse(
                content="",
                action=ActionCall(cmd="done", stdin="Recovered from loop"),
                prompt_tokens=140,
                completion_tokens=30,
            ),
        ]
    )
    harness = Harness(db_path=tmp_path / "tether.db", tools=[ping, "edit"], provider=provider)
    session = await harness.run("Ping example.com once")
    assert session.status == "COMPLETED"
    assert session.result == "Recovered from loop"
    assert call_count == 1
    assert session.total_prompt_tokens == 600
    assert session.total_completion_tokens == 120
    turns = [t for t in harness.store.get_turns(session.id) if t.role == "assistant"]
    assert [t.event_type for t in turns] == [
        "syntax_error",
        "tool_error",
        "ok",
        "loop_stall",
        "completed",
    ]
    step5_prompt = "\n".join(m["content"] for m in provider.recorded_calls[4])
    assert "[LOOP DETECTED]" in step5_prompt


async def test_harness_lifecycle_and_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover worker spawn, skill resolution, late inbox messages, max_steps, and provider errors."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    s1 = store.create_session("Goal 1")

    monkeypatch.setattr(
        "tether.harness.subprocess.Popen",
        lambda *a, **kw: type("FakePopen", (), {"pid": 4242})(),
    )
    assert spawn_detached_worker(tmp_path / "tether.db", s1.id) == 4242

    sk_dir = tmp_path / "skills"
    sk_dir.mkdir(exist_ok=True)
    (sk_dir / "helper.md").write_text(
        "---\nname: helper\nmodel: ollama/qwen3.5:9b\ntools: [web]\n---\nHelp instructions",
        encoding="utf-8",
    )
    custom_sk = sk_dir / "custom_sk"
    custom_sk.mkdir(exist_ok=True)
    (custom_sk / "SKILL.md").write_text(
        "---\nname: custom_sk\ndescription: Custom\ntools: [web, custom-op]\n---\nUse custom-op.",
        encoding="utf-8",
    )
    (custom_sk / "tools.py").write_text(
        "from tether import tool\n"
        "@tool(name='custom-op')\n"
        "def custom_op() -> str:\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    def plain_fn(x: str) -> str:
        return x

    h = Harness(
        db_path=tmp_path / "tether.db",
        skill="helper",
        tools=[plain_fn, plain_fn, ToolSpec("t2", "d", plain_fn, [], False, False)],
        skill_search_dirs=[sk_dir],
    )
    h2 = Harness(db_path=tmp_path / "tether.db", tools="all")
    assert "web" in h2._enabled_tool_names

    sid_spawned = h.spawn("Spawned goal")
    assert sid_spawned.startswith("ses_")

    with pytest.raises(ValueError, match="not found"):
        await h.send("ses_missing", "msg")
    with pytest.raises(ValueError, match="not found"):
        await h.execute_session("ses_missing")

    store.update_session(sid_spawned, status="RUNNING")
    assert (await h.send(sid_spawned, "while running")).status == "RUNNING"
    store.update_session(sid_spawned, status="COMPLETED")
    assert (await h.send(sid_spawned, "resume headless", headless=True)).status == "PENDING"

    step_idx = 0

    class ScriptedProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            nonlocal step_idx
            step_idx += 1
            if step_idx == 1:
                return ModelResponse(content="Thinking out loud without calling act")
            if step_idx == 2:
                store.enqueue_inbox(s_nudge.id, "Wait, add one more detail!")
                return ModelResponse(content="", action=ActionCall(cmd="done", stdin="First draft"))
            return ModelResponse(content="", action=ActionCall(cmd="done", stdin="Final draft"))

    register_provider("harness-mock", lambda name: ScriptedProvider())
    h_nudge = Harness(
        db_path=tmp_path / "tether.db",
        model="harness-mock/qwen",
        provider=ScriptedProvider(),
        max_steps=5,
        skill_search_dirs=[sk_dir],
    )
    s_nudge = h_nudge.create_session("Nudge & late inbox test")
    store.update_session(s_nudge.id, status="PENDING")
    s_with_skill = store.create_session(
        "Skill session", model="harness-mock/qwen", skill="custom_sk"
    )

    done_rec = await h_nudge.execute_session(s_nudge.id)
    assert done_rec.status == "COMPLETED" and done_rec.result == "Final draft"

    step_idx = 2
    done_sk = await h_nudge.execute_session(s_with_skill.id)
    assert done_sk.status == "COMPLETED"

    class NeverDoneProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            return ModelResponse(content="Still thinking...")

    h_max = Harness(db_path=tmp_path / "tether.db", provider=NeverDoneProvider(), max_steps=2)
    s_max = await h_max.run("Never finishes")
    assert s_max.status == "FAILED" and "Max steps" in (s_max.result or "")

    class CrashProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            raise RuntimeError("provider exploded")

    h_crash = Harness(db_path=tmp_path / "tether.db", provider=CrashProvider(), max_steps=2)
    s_crash = await h_crash.run("Crash test")
    assert s_crash.status == "FAILED" and "provider exploded" in (s_crash.result or "")


async def test_pre_done_verification_gates_and_self_healing(tmp_path: Path) -> None:
    """Verify failing pre-done gate blocks completion, feeds stderr back, and self-heals."""
    from tether.sandbox import SandboxPolicy

    ws = tmp_path / "ws"
    ws.mkdir()
    target_file = ws / "module.py"
    target_file.write_text("VALUE = 1\n", encoding="utf-8")

    provider = FakeScriptedProvider(
        [
            # Step 1: Agent prematurely calls done while VALUE != 42
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Premature completion")),
            # Step 2: Agent sees [VERIFICATION GATE FAILED] and fixes module.py
            ModelResponse(
                content="",
                action=ActionCall(cmd="edit write module.py", stdin="VALUE = 42\n"),
            ),
            # Step 3: Agent calls done again; gate now exits 0
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Verified deliverable")),
        ]
    )

    sandbox = SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False)
    gate_cmd = "python3 -c 'import module, sys; sys.exit(0 if module.VALUE == 42 else 1)'"
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=["edit"],
        verify=[gate_cmd],
        sandbox=sandbox,
        provider=provider,
    )

    session = await harness.run("Set VALUE = 42 in module.py")
    assert session.status == "COMPLETED"
    assert session.result == "Verified deliverable"
    assert session.step_count == 3

    # Verify step 2 prompt included the deterministic verification gate failure diagnostic
    step2_prompt = "\n".join(m["content"] for m in provider.recorded_calls[1])
    assert "[VERIFICATION GATE FAILED:" in step2_prompt
    assert "Fix the reported issues before calling `done` again." in step2_prompt


async def test_verification_gate_circuit_breaker_and_skill_verify(tmp_path: Path) -> None:
    """Verify circuit breaker trips on consecutive gate failures and skills declare verify gates."""
    from tether.sandbox import SandboxPolicy

    ws = tmp_path / "ws_cb"
    ws.mkdir()
    sk_dir = tmp_path / "skills"
    sk_dir.mkdir()
    (sk_dir / "strict.md").write_text(
        "---\n"
        "name: strict\n"
        "description: Strict verifier\n"
        "tools: [bash]\n"
        "verify:\n"
        "  - python3 -c \"import sys; print('X' * 2500); sys.exit(2)\"\n"
        "---\n"
        "Always pass verification.",
        encoding="utf-8",
    )

    provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Try 1")),
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Try 2")),
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Try 3")),
        ]
    )

    sandbox = SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False)
    harness = Harness(
        db_path=tmp_path / "tether.db",
        skill="strict",
        verify="echo ok",
        max_verify_failures=2,
        sandbox=sandbox,
        provider=provider,
        skill_search_dirs=[sk_dir],
    )
    session = await harness.run("Test circuit breaker")
    assert session.status == "FAILED"
    assert "consecutive times" in (session.result or "")
    assert session.step_count == 2

    # Also test sandbox violation inside verification gate (e.g., blocked sudo command)
    bad_gate_provider = FakeScriptedProvider(
        [
            ModelResponse(content="", action=ActionCall(cmd="done", stdin="Try bad gate")),
        ]
    )
    h_bad = Harness(
        db_path=tmp_path / "tether.db",
        verify=["sudo rm -rf /"],
        max_verify_failures=1,
        sandbox=sandbox,
        provider=bad_gate_provider,
    )
    s_bad = await h_bad.run("Bad gate command")
    assert s_bad.status == "FAILED"


async def test_waiting_input_and_interactive_inquiry(tmp_path: Path) -> None:
    """Verify `done --ask` pauses in WAITING_INPUT, handles late inbox, and resumes on `send`."""
    store = SQLiteStore(db_path=tmp_path / "tether.db")
    provider = FakeScriptedProvider(
        [
            # Step 1: Agent asks a clarifying question via done --ask
            ModelResponse(
                content="",
                action=ActionCall(cmd="done --ask", stdin="Target environment: staging or prod?"),
            ),
            # Step 2 (after user answers via send): Agent completes task
            ModelResponse(
                content="",
                action=ActionCall(cmd="done", stdin="Deployed to staging as requested."),
            ),
        ]
    )
    harness = Harness(db_path=tmp_path / "tether.db", provider=provider)
    paused = await harness.run("Deploy the service")
    assert paused.status == "WAITING_INPUT"
    assert paused.result == "Target environment: staging or prod?"
    assert "waiting for input" in store.get_session_digest(paused.id)

    resumed = await harness.send(paused.id, "Use staging.")
    assert resumed.status == "COMPLETED"
    assert resumed.result == "Deployed to staging as requested."
    step2_prompt = "\n".join(m["content"] for m in provider.recorded_calls[1])
    assert "[WAITING_INPUT] Target environment: staging or prod?" in step2_prompt
    assert "[Follow-up instruction]: Use staging." in step2_prompt

    # Also verify late inbox arrival during `done --ask` continues without suspending
    late_step = 0

    class LateInboxAskProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            nonlocal late_step
            late_step += 1
            if late_step == 1:
                store.enqueue_inbox(s_late.id, "Already answered: use Python 3.12")
                return ModelResponse(
                    content="",
                    action=ActionCall(cmd="done --ask 'Which Python version?'"),
                )
            return ModelResponse(content="", action=ActionCall(cmd="done 'Used Python 3.12'"))

    h_late = Harness(db_path=tmp_path / "tether.db", provider=LateInboxAskProvider())
    s_late = h_late.create_session("Late inbox on ask")
    done_late = await h_late.execute_session(s_late.id)
    assert done_late.status == "COMPLETED"
    assert done_late.result == "Used Python 3.12"
