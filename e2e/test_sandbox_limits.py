"""Resource limits (#124 item 6). Scripted: the proxy forces the command, so the result never
depends on the model; tether alone must stop it and name the limit with an Instead: hint."""

from __future__ import annotations

import sys

import pytest

from e2e.conftest import Tether

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="rlimits are Linux only")


def test_cpu_limit_hit_is_named_with_a_hint(tether: Tether, chaos) -> None:
    chaos.script("bash while :; do :; done", ("done", "ok"))
    r = tether.run("spin", "--tools", "bash", "--limit", "cpu=1")
    out = tether.tool_outputs(r["id"])[0]
    assert out.strip().splitlines()[-1].startswith("[limit hit: cpu 1s] Instead:"), out


def test_fsize_limit_hit_is_named(tether: Tether, chaos) -> None:
    chaos.script("bash head -c 3000000 /dev/zero > big.bin", ("done", "ok"))
    r = tether.run("write", "--tools", "bash", "--limit", "fsize=1")
    assert "[limit hit: fsize 1 MB]" in tether.tool_outputs(r["id"])[0]
    assert (tether.ws / "big.bin").stat().st_size <= 1024 * 1024


def test_no_limit_leaves_output_alone(tether: Tether, chaos) -> None:
    chaos.script("bash echo hi", ("done", "ok"))
    r = tether.run("echo", "--tools", "bash")
    assert "[limit hit" not in tether.tool_outputs(r["id"])[0]


def test_bad_limit_is_a_usage_error(tether: Tether, chaos) -> None:
    p = tether.cli("run", "--limit", "bogus=1", "x")
    assert p.returncode == 1 and "--limit" in p.stderr
