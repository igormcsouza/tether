"""Recorded model thinking (#32). Scripted: the proxy plays the model, tether is real.

The proxy's Ollama reply has no `thinking` field, so the fixture wraps the reply format for this
module only (monkeypatched, so no file outside this test changes).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from e2e import proxy
from e2e.conftest import Tether

THINK = "secret reasoning about the plan xyz"


@pytest.fixture
def thinking(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, bool]]:
    """Scripted Ollama replies carry `message.thinking` while `state['on']` is set."""
    state = {"on": True}
    base = proxy._ollama

    def with_thinking(action: Any, n: int) -> dict[str, Any]:
        resp = base(action, n)
        if state["on"]:
            resp["message"]["thinking"] = THINK
        return resp

    monkeypatch.setitem(proxy._FORMATS, "/api/chat", with_thinking)
    yield state


def test_thinking_is_recorded_and_read_back_with_the_tool_call(
    tether: Tether, chaos, thinking
) -> None:
    chaos.script("bash true", ("done", "ok"))
    r = tether.run("think", "--tools", "bash")
    assert r["rc"] == 0 and r["status"] == "COMPLETED"
    p = tether.cli("read", r["id"], "--thinking")
    assert p.returncode == 0, p.stderr
    assert THINK in p.stdout


def test_thinking_never_reaches_a_later_request(tether: Tether, chaos, thinking) -> None:
    chaos.script("bash true", ("done", "ok"))
    r = tether.run("think again", "--tools", "bash")
    assert r["status"] == "COMPLETED"
    assert len(chaos.requests) >= 2, "need a request after the thinking reply"
    for req in chaos.requests[1:]:
        assert THINK not in json.dumps(req), "thinking must not be sent back to the model"
    assert all(THINK not in out for out in tether.tool_outputs(r["id"]))


def test_read_thinking_on_a_session_without_thinking_says_so(
    tether: Tether, chaos, thinking
) -> None:
    thinking["on"] = False
    chaos.script(("done", "ok"))
    r = tether.run("plain", "--tools", "bash")
    assert r["status"] == "COMPLETED"
    p = tether.cli("read", r["id"], "--thinking")
    assert "no thinking recorded" in p.stdout + p.stderr
