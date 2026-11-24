"""`done, stdin="13"` typed into cmd delivers the answer, as in the Coding Ladder shell-1 run
(qwen3.5:9b typed the Python call into cmd). What tether sends and records (no model)."""

from __future__ import annotations

from e2e.conftest import Tether


def test_done_with_stdin_typed_into_cmd_completes_with_the_answer(tether: Tether, chaos) -> None:
    chaos.script("echo 13 > answer.txt", 'done, stdin="13"')
    r = tether.run("write 13 into answer.txt, then report it", "--tools", "bash")
    assert (tether.ws / "answer.txt").read_text() == "13\n"
    assert (r["rc"], r["status"], r["result"]) == (0, "COMPLETED", "13"), r
