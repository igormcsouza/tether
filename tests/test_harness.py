"""Unit tests for tether/harness.py (agent loop, loop-stall breaker, worker spawn, recovery)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, register_provider, tool
from tether.decorator import ToolSpec
from tether.harness import detect_cycle, spawn_detached_worker
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

    store.update_session(sid_spawned, status="RUNNING", pid=os.getpid())
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


@pytest.mark.parametrize(
    "gate",
    ["sudo rm -rf /", "tether_no_such_cmd_xyz", "exit 127", "exit 124"],
    ids=["sandbox_violation", "not_found", "127", "timeout"],
)
async def test_broken_gate_fails_immediately_as_gate_error(tmp_path: Path, gate: str) -> None:
    """A gate that errors (not fails) ends the session at once with gate_error and exit 3."""
    from tether.api import exit_code, failure_info
    from tether.sandbox import SandboxPolicy

    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd="done", stdin="x"))] * 3
    )
    harness = Harness(
        db_path=tmp_path / "tether.db",
        verify=[gate],
        max_verify_failures=3,
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
        provider=provider,
    )
    session = await harness.run("Broken gate")
    assert session.status == "FAILED"
    assert session.step_count == 1
    assert f"Verification gate `{gate}` misconfigured:" in (session.result or "")
    fail = failure_info(session)
    assert fail is not None and fail["kind"] == "gate" and fail["gate"] == gate
    assert exit_code(session) == 3
    turns = harness.store.get_turns(session.id)
    assert [t.event_type for t in turns if t.role == "assistant"] == ["gate_error"]
    assert "misconfigured, not your work" in turns[-1].content


async def test_normal_nonzero_gate_still_retries_as_gate_fail(tmp_path: Path) -> None:
    """A gate command that ran and exited non-zero stays a retryable gate_fail."""
    from tether.sandbox import SandboxPolicy

    provider = FakeScriptedProvider(
        [ModelResponse(content="", action=ActionCall(cmd="done", stdin="x"))] * 2
    )
    harness = Harness(
        db_path=tmp_path / "tether.db",
        verify=["exit 2"],
        max_verify_failures=2,
        sandbox=SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False),
        provider=provider,
    )
    session = await harness.run("Real failure")
    assert session.status == "FAILED"
    assert session.step_count == 2
    assert "failed 2 consecutive times" in (session.result or "")
    events = [t.event_type for t in harness.store.get_turns(session.id) if t.role == "assistant"]
    assert events == ["gate_fail", "gate_fail"]


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


def test_detect_cycle_patterns() -> None:
    a, b, c, d = ("a", None), ("b", None), ("c", None), ("d", None)
    assert detect_cycle([a, b, a, b, a, b]) == ["a", "b"]
    assert detect_cycle([d, a, b, c, a, b, c]) == ["a", "b", "c"]
    assert detect_cycle([a, b, a, b]) is None  # test/view/test/view is normal work
    assert detect_cycle([a, b, c, a, b]) is None
    assert detect_cycle([a, a, a, a, a, a]) is None  # identical run is loop_stall's job
    assert detect_cycle([a, b, c, d]) is None
    assert detect_cycle([a, b, a, b, a, b], window=5) is None  # window cuts the history


class _Run:
    def __init__(self, session: Any, provider: Any, events: list[str], calls: list[str]) -> None:
        self.session, self.provider, self.events, self.calls = session, provider, events, calls


class _InboxOnCall(FakeScriptedProvider):
    """Enqueues a follow-up message while generating the `at`-th reply."""

    def __init__(self, responses: list[ModelResponse], store: SQLiteStore, at: int) -> None:
        super().__init__(responses)
        self.store, self.at, self.session_id = store, at, ""

    async def generate(self, messages: Any, tools: Any) -> ModelResponse:
        if len(self.recorded_calls) + 1 == self.at:
            self.store.enqueue_inbox(self.session_id, "keep going")
        return await super().generate(messages, tools)


async def _run_commands(tmp_path: Path, cmds: list[str], inbox_at: int = 0) -> _Run:
    calls: list[str] = []

    @tool(name="ping", description="Ping a host")
    def ping(host: str) -> str:
        calls.append(host)
        return "pong"

    script = [
        ModelResponse(content="", action=ActionCall(cmd=c), prompt_tokens=10, completion_tokens=5)
        for c in cmds
    ]
    script.append(
        ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"), prompt_tokens=10)
    )
    db = tmp_path / "tether.db"
    provider = _InboxOnCall(script, SQLiteStore(db_path=db), inbox_at)
    harness = Harness(db_path=db, tools=[ping], provider=provider)
    rec = harness.create_session("goal")
    provider.session_id = rec.id
    session = await harness.execute_session(rec.id)
    events = [t.event_type for t in harness.store.get_turns(session.id) if t.role == "assistant"]
    return _Run(session, provider, events, calls)


async def test_cycle_stall_three_command_cycle(tmp_path: Path) -> None:
    run = await _run_commands(tmp_path, [f"ping {h}.com" for h in "abcabc"])
    assert run.session.status == "COMPLETED"
    assert run.events == ["ok"] * 5 + ["cycle_stall", "completed"]
    assert run.calls == ["a.com", "b.com", "c.com", "a.com", "b.com"]
    nudge = "\n".join(m["content"] for m in run.provider.recorded_calls[6])
    assert "[CYCLE DETECTED]" in nudge
    assert "`ping a.com` -> `ping b.com` -> `ping c.com`" in nudge
    assert "may not have changed" in nudge


async def test_cycle_stall_two_command_cycle(tmp_path: Path) -> None:
    cmds = ["ping 1,40p", "ping 40,100p"] * 3
    run = await _run_commands(tmp_path, cmds)
    assert run.events == ["ok"] * 5 + ["cycle_stall", "completed"]


async def test_test_view_pairs_twice_do_not_cycle_stall(tmp_path: Path) -> None:
    run = await _run_commands(tmp_path, ["ping t", "ping v", "ping t", "ping v"])
    assert run.events == ["ok"] * 4 + ["completed"]
    assert len(run.calls) == 4


async def test_varied_commands_do_not_cycle_stall(tmp_path: Path) -> None:
    run = await _run_commands(tmp_path, [f"ping h{i}" for i in range(6)])
    assert "cycle_stall" not in run.events


async def test_identical_run_stays_loop_stall(tmp_path: Path) -> None:
    run = await _run_commands(tmp_path, ["ping x"] * 4)
    assert run.events == ["ok", "loop_stall", "loop_stall", "loop_stall", "completed"]


async def test_cycle_history_resets_on_inbox_message(tmp_path: Path) -> None:
    # Message consumed before step 5: a,b,a,b | a,b must not fire as a 6-action cycle.
    run = await _run_commands(tmp_path, ["ping a", "ping b"] * 3, inbox_at=4)
    assert "cycle_stall" not in run.events


async def test_cycle_history_resets_after_nudge(tmp_path: Path) -> None:
    run = await _run_commands(tmp_path, [f"ping {h}" for h in "abcabc" * 2])
    assert run.events == ["ok"] * 5 + ["cycle_stall"] + ["ok"] * 5 + ["cycle_stall", "completed"]


async def test_quiet_nudge_after_six_quiet_steps(tmp_path: Path) -> None:
    # First command is a change (ping), then 8 quiet commands (bash cat)
    # Nudge should appear on the 6th quiet command (bash cat f5)
    cmds = ["ping a.com"] + [f"bash cat f{i}" for i in range(8)]
    run = await _run_commands(tmp_path, cmds)

    # Check that exactly one observation contains the nudge
    observations = run.provider.store.list_observations(run.session.id)
    nudge_obs = [o for o in observations.values() if "[NUDGE]" in o.raw_output]
    assert len(nudge_obs) == 1, f"Expected exactly one nudge, got {len(nudge_obs)}"

    # The nudge should be on the 6th quiet command (step 7: ping + 6 quiet = step 7)
    # Observations are 1-indexed by step
    assert nudge_obs[0].step == 7, f"Nudge at step {nudge_obs[0].step}, expected 7"

    # Also verify is_quiet function directly
    from tether.harness import is_quiet

    assert is_quiet("bash cat x")
    assert not is_quiet("ping a.com")
    assert is_quiet("git diff")
    assert not is_quiet("git commit -m x")
    assert not is_quiet("")


async def test_empty_api_key_env_fails_session_naming_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "providers.yaml"
    cfg.write_text(
        "acme:\n  kind: openai\n  base_url: http://x/v1\n  api_key_env: ACME_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TETHER_PROVIDERS", str(cfg))
    for value in ("", None):  # empty and unset behave the same
        if value is None:
            monkeypatch.delenv("ACME_KEY", raising=False)
        else:
            monkeypatch.setenv("ACME_KEY", value)
        harness = Harness(db_path=tmp_path / "t.db", model="acme/m")
        rec = harness.create_session("goal")
        done = await harness.execute_session(rec.id)
        assert done.status == "FAILED" and done.result is not None
        assert done.result.startswith("Worker error: ProviderError:")
        assert "`ACME_KEY`" in done.result


async def test_resolve_value_error_fails_session_with_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "providers.yaml"
    cfg.write_text("acme: [not, a, mapping]\n", encoding="utf-8")
    monkeypatch.setenv("TETHER_PROVIDERS", str(cfg))
    harness = Harness(db_path=tmp_path / "t.db", model="acme/m")
    rec = harness.create_session("goal")
    done = await harness.execute_session(rec.id)
    assert done.status == "FAILED" and done.result is not None
    assert done.result.startswith("Worker error: ValueError: providers.yaml")
    assert [t.event_type for t in harness.store.get_turns(rec.id)] == ["tool_error"]


async def test_send_extends_exhausted_session_ceiling(tmp_path: Path) -> None:
    """#75: `max_steps` is an absolute ceiling; resuming an exhausted session extends it."""

    class NeverDoneProvider:
        model_name = "qwen3.5:9b"

        async def generate(self, messages: Any, tools: Any) -> ModelResponse:
            return ModelResponse(content="Still thinking...")

    h = Harness(db_path=tmp_path / "t.db", provider=NeverDoneProvider(), max_steps=3)
    first = await h.run("goal")
    assert (first.status, first.step_count, first.max_steps) == ("FAILED", 3, 3)

    second = await h.send(first.id, "go on")
    assert (second.status, second.step_count, second.max_steps) == ("FAILED", 6, 6)

    # a session paused early keeps its larger remaining budget (no extension)
    paused = h.create_session("g2")
    h.store.update_session(paused.id, status="WAITING_INPUT", step_count=1, max_steps=10)
    resumed = await h.send(paused.id, "continue")
    assert (resumed.step_count, resumed.max_steps) == (10, 10)
