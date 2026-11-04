"""bench/ladder/run.py: a Claude Haiku provider through tether, and the failure fed into a retry."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

LADDER = Path(__file__).resolve().parent.parent / "bench" / "ladder"


@pytest.fixture
def lad(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(LADDER))
    spec = importlib.util.spec_from_file_location("ladder_run_t", LADDER / "run.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ladder_run_t"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_haiku_is_a_provider_routed_through_tether_and_the_claude_cli(lad) -> None:
    assert lad.PROVIDERS["claude-softmedium"]["prefix"] == "claude-softmedium/"
    task = lad.T.TASKS["write-1"]
    cmd = lad.harness_cmd(
        "tether", "haiku", task, 32000, Path("/rd"), Path("/ws"), "tether",
        False, False, [], 30, None, "claude-softmedium",
    )  # fmt: skip
    assert cmd[cmd.index("--model") + 1] == "claude-softmedium/haiku"
    assert cmd[cmd.index("--context-tokens") + 1] == "32000"
    assert not any(a.startswith("think=") for a in cmd), "Haiku has no think parameter"


def test_retry_goal_adds_what_the_previous_attempt_did(lad) -> None:
    task = lad.T.TASKS["bugfix-2"]
    assert lad.retry_goal(task, None) == task.goal
    prev = {
        "score": 0.375, "detail": "3/8 hidden tests", "run_status": "timeout",
        "session_status": "RUNNING",
    }  # fmt: skip
    goal = lad.retry_goal(task, prev)
    assert goal.startswith(task.goal)
    assert "3/8 hidden tests" in goal and "did not pass" in goal
    assert len(goal) < len(task.goal) + 400, "a bounded hint, not a transcript"


def test_harness_cmd_takes_the_goal_it_is_given(lad) -> None:
    task = lad.T.TASKS["write-1"]
    cmd = lad.harness_cmd(
        "tether", "qwen3.5:9b", task, 8192, Path("/rd"), Path("/ws"), "tether",
        False, True, [], 30, None, "ollama", goal="RETRY GOAL",
    )  # fmt: skip
    assert cmd[-1] == "RETRY GOAL"


def test_the_second_attempt_gets_the_first_attempts_record(
    lad, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list = []

    def fake(model, task, attempt, ctx, out, tether_bin, wall, can_think=True, harness="tether",
             provider="ollama", prev=None):  # fmt: skip
        seen.append((task.id, attempt, prev))
        return {"model": model, "task": task.id, "kind": task.kind, "tier": task.tier,
                "attempt": attempt, "think": False, "params": [], "max_steps": 30,
                "fold_after": None, "ctx": ctx, "wall_s": 1, "run_status": "ok",
                "delivered_steps": None, "score": 0.25, "pass": False,
                "detail": "2/8 hidden tests", "harness": harness}  # fmt: skip

    monkeypatch.setattr(lad, "run_attempt", fake)
    monkeypatch.setattr(lad, "capabilities", lambda m: [])
    monkeypatch.setattr(
        sys, "argv",
        ["run.py", "--out", str(tmp_path), "--models", "haiku", "--provider", "claude-softmedium",
         "--kinds", "write", "--max-tier", "1", "--attempts", "2"],
    )  # fmt: skip
    lad.main()
    assert [(t, a) for t, a, _ in seen] == [("write-1", 0), ("write-1", 1)]
    assert seen[0][2] is None
    assert seen[1][2] and seen[1][2]["detail"] == "2/8 hidden tests"
