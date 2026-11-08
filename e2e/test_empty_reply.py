"""Empty model replies (#135): asked again once, and three in a row hand the session back.

Scripted: the proxy plays the model, tether is real. An empty reply is no text and no tool call.
"""

from __future__ import annotations

from e2e.conftest import Tether

EMPTY = {"text": ""}  # the proxy answers an assistant message with no content and no tool_calls


def test_empty_reply_is_asked_again_once(tether: Tether, chaos) -> None:
    chaos.script(EMPTY, ("done", "ok"))
    r = tether.run("answer")
    assert (r["rc"], r["status"]) == (0, "COMPLETED"), r
    assert len(chaos.requests) == 2, "one empty reply is asked again within the same turn"
    assert chaos.requests[0]["messages"] == chaos.requests[1]["messages"], (
        "the retry is the same payload"
    )


def test_real_reply_after_an_empty_one_goes_on(tether: Tether, chaos) -> None:
    chaos.script(EMPTY, ("done", "after empty"))
    r = tether.run("answer")
    assert (r["rc"], r["status"], r["result"]) == (0, "COMPLETED", "after empty"), r
    assert len(chaos.requests) == 2


def test_three_empty_turns_in_a_row_wait_for_input(tether: Tether, chaos) -> None:
    # each turn is two empty requests (the ask-again), so three turns are six empty replies
    chaos.script(*[EMPTY] * 6)
    r = tether.run("answer")
    assert (r["rc"], r["status"]) == (2, "WAITING_INPUT"), r
    assert "scripted" in r["result"], "the result names the model"
    assert "think=false" in r["result"], "the result suggests think=false"
    assert len(chaos.requests) == 6, "no fourth turn after the third empty one"
