"""H1: a scripted session out of steps gets one final-answer turn, and its text is the answer.

Scripted replies, so the result never depends on the model.
"""

from __future__ import annotations

from e2e.conftest import Tether


def test_final_answer_turn_keeps_the_plain_text_reply(tether: Tether, chaos) -> None:
    # 3 lookups use up the 3 steps; the next request is the final-answer turn and gets plain text
    chaos.script("ls a", "ls b", "ls c", {"text": "Found the files a, b and c."})
    r = tether.run("look around", "--tools", "bash", "--max-steps", "3")
    assert (r["rc"], r["status"]) == (2, "WAITING_INPUT"), r
    assert (r["result"] or "").startswith("Found the files a, b and c.\n\n[STUCK: out of steps"), r
