"""Documented pattern: --no-network keeps the model's bash offline (see the tutorial)."""

from __future__ import annotations

import shutil

import pytest

from e2e.conftest import Tether

PROBE = "bash curl -sS -m 3 http://1.1.1.1 >/dev/null 2>&1; echo rc=$?"


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="--no-network needs bwrap")
def test_no_network_blocks_model_bash(tether: Tether, chaos) -> None:
    chaos.script(PROBE, ("done", "ok"))
    r = tether.run("probe network", "--tools", "bash", "--no-network")
    assert r["rc"] == 0, r["stderr"]
    out = tether.tool_outputs(r["id"])[0]
    assert "rc=0" not in out, out
