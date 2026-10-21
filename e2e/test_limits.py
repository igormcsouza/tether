"""Resource limits: network isolation and the hard context budget."""

from __future__ import annotations

import json
import shutil
from urllib.parse import urlparse

import pytest

from e2e.conftest import Tether


@pytest.mark.skipif(not shutil.which("bwrap"), reason="--no-network needs bubblewrap")
def test_no_network_blocks_what_the_default_allows(tether: Tether, chaos) -> None:
    port = urlparse(chaos.url).port
    probe = f"bash python3 -c \"import socket;socket.create_connection(('127.0.0.1',{port}),2)\""
    chaos.script(probe, ("done", "ok"))
    control = tether.run("probe", "--tools", "bash")
    assert "exit 0" in tether.tool_outputs(control["id"])[0], "control: the proxy must be reachable"
    chaos.requests.clear()
    chaos.script(probe, ("done", "ok"))
    r = tether.run("probe", "--tools", "bash", "--no-network")
    assert "exit 0" not in tether.tool_outputs(r["id"])[0], "--no-network must cut the connection"


def _size(req: dict) -> int:
    return len(json.dumps(req["messages"])) // 4  # ~tokens, same estimator family as tether


def test_hard_context_budget_trims_old_history(tether: Tether, chaos) -> None:
    big = "bash python3 -c \"print('y'*1500)\""
    chaos.script(*[big] * 8, ("done", "ok"))
    tether.run("budget", "--tools", "bash", "--context-tokens", "700", "--max-steps", "10")
    assert len(chaos.requests) >= 9
    for req in chaos.requests:
        assert _size(req) <= 700 * 1.3, f"prompt grew past the budget: ~{_size(req)} tokens"
        assert req["messages"][0]["role"] == "system" and "Goal: budget" in json.dumps(
            req["messages"][:3]
        )
    chaos.requests.clear()
    chaos.script(*[big] * 8, ("done", "ok"))
    tether.run("budget", "--tools", "bash", "--max-steps", "10")  # default 8192 budget: no trimming
    assert _size(chaos.requests[-1]) > 700 * 1.3, "control: without the small budget history grows"
