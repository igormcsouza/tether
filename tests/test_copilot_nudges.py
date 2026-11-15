"""F3 nudges: last-step notice, lookup-only nudges, and the way out of a wrong gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.conftest import FakeScriptedProvider
from tether import ActionCall, Harness, ModelResponse, tool
from tether.context import restart_message

ASK = (
    "If the test or gate itself is wrong, do not fight it: "
    "call `done --ask` and say which one and why."
)


async def _session(
    tmp_path: Path,
    cmds: list[str],
    *,
    tools: list[Any] | None = None,
    max_steps: int = 15,
    verify: str | None = None,
) -> Any:
    @tool(name="ping", description="Ping a host")
    def ping(host: str) -> str:
        return "pong"

    script = [
        ModelResponse(content="", action=ActionCall(cmd=c), prompt_tokens=10, completion_tokens=5)
        for c in cmds
    ]
    script.append(
        ModelResponse(content="", action=ActionCall(cmd="done", stdin="ok"), prompt_tokens=10)
    )
    extra: dict[str, Any] = {"verify": verify} if verify else {}
    harness = Harness(
        db_path=tmp_path / "tether.db",
        tools=tools or [ping],
        provider=FakeScriptedProvider(script),
        max_steps=max_steps,
        **extra,
    )
    rec = harness.create_session("goal")
    session = await harness.execute_session(rec.id)
    return harness.store.list_observations(session.id)


def _steps(obs: Any, needle: str) -> list[int]:
    return sorted(o.step for o in obs.values() if needle in o.raw_output)


async def test_last_step_notice_once_on_the_step_before_the_limit(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [f"ping h{i}.com" for i in range(7)], max_steps=8)
    assert _steps(obs, "[LAST STEP]") == [7]
    assert "Call `done` now with your answer: what you found or did, and what is left." in (
        next(o for o in obs.values() if o.step == 7).raw_output
    )


async def test_no_last_step_notice_below_the_minimum_budget(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [f"ping h{i}.com" for i in range(6)], max_steps=7)
    assert _steps(obs, "[LAST STEP]") == []


async def test_steps_left_without_a_change_asks_for_the_answer(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [f"bash cat f{i}" for i in range(11)], max_steps=12)
    assert _steps(obs, "steps left") == [9]
    assert "3 steps left. Call `done` with your answer before they run out." in next(
        o.raw_output for o in obs.values() if "steps left" in o.raw_output
    )


async def test_steps_left_after_a_change_keeps_the_edit_wording(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [f"ping h{i}.com" for i in range(11)], max_steps=12)
    assert _steps(obs, "steps left") == [9]
    assert "Finish the current edit, then call `done`" in next(
        o.raw_output for o in obs.values() if "steps left" in o.raw_output
    )


async def test_lookup_nudge_when_neither_bash_nor_edit_is_enabled(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [f"bash cat f{i}" for i in range(14)])
    assert _steps(
        obs,
        "[NUDGE] 12 lookups and no answer yet. "
        "Call `done` with what you found, or do one more lookup.",
    ) == [12]


async def test_explore_nudge_keeps_edit_wording_when_edit_is_enabled(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [f"bash cat f{i}" for i in range(14)], tools=["edit", "bash"])
    assert _steps(
        obs,
        "[NUDGE] No file changes in 12 steps. Make your edit now, "
        "or call `done` with what you found.",
    ) == [12]


def test_restart_after_a_failing_check_offers_done_ask() -> None:
    msg = restart_message(
        step=9,
        check_cmd="pytest -q",
        failing_output="FAILED t",
        files={"a.py": "x"},
        tried=["edit a.py"],
        failing=["t"],
    )
    assert msg.count(ASK) == 1


def test_fresh_restart_after_a_failing_check_offers_done_ask() -> None:
    msg = restart_message(
        step=9,
        check_cmd="pytest -q",
        failing_output=None,
        files={},
        tried=[],
        fresh=["a.py"],
        failing=["t"],
    )
    assert msg.count(ASK) == 1


def test_handback_does_not_offer_done_ask() -> None:
    msg = restart_message(
        step=9,
        check_cmd="pytest -q",
        failing_output="FAILED t",
        files={},
        tried=[],
        handback=2,
    )
    assert ASK not in msg


async def test_failed_gate_on_done_offers_done_ask(tmp_path: Path) -> None:
    obs = await _session(tmp_path, [], verify="false")
    gates = [o for o in obs.values() if "[VERIFICATION GATE FAILED" in o.raw_output]
    assert gates
    assert all(o.raw_output.count(ASK) == 1 for o in gates)
