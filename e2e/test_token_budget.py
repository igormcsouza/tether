"""Token budget: `tether run --max-tokens` pauses; `tether send` resumes. Scripted."""

from __future__ import annotations

from e2e.conftest import Tether


def test_budget_crossing_pauses_with_exit_2_before_the_next_model_call(
    tether: Tether, chaos
) -> None:
    chaos.script("bash true", ("done", "ok"))
    r = tether.run("spend", "--tools", "bash", "--max-tokens", "1")
    assert (r["rc"], r["status"]) == (2, "WAITING_INPUT"), r
    assert r["result"].startswith("[TOKEN BUDGET] used "), r["result"]
    assert "of 1 tokens" in r["result"], r["result"]
    assert len(chaos.requests) == 1, "the budget is checked before the next model call"


def test_send_resumes_a_budget_paused_session(tether: Tether, chaos) -> None:
    chaos.script("bash true", ("done", "ok"))
    paused = tether.run("spend", "--tools", "bash", "--max-tokens", "1")
    assert paused["rc"] == 2, paused
    r = tether.send(paused["id"], "keep going")
    assert (r["rc"], r["status"], r["result"]) == (0, "COMPLETED", "ok"), r
    assert len(chaos.requests) == 2
    assert "keep going" in str(chaos.requests[1]["messages"]), (
        "the human's reply must reach the model"
    )


def test_non_positive_budget_is_a_usage_error(tether: Tether, chaos) -> None:
    p = tether.cli("run", "--model", "e2e/scripted", "--max-tokens", "0", "spend")
    assert p.returncode == 1, p
    assert "--max-tokens must be a positive integer" in p.stdout + p.stderr
    assert not chaos.requests, "a rejected budget must never reach the model"
