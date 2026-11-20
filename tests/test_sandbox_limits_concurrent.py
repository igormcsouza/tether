"""A SIGKILL is not a cpu-limit hit just because another command burned CPU meanwhile (#303)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from tether import SandboxPolicy

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="rlimits are enforced on Linux")

BURN = (
    'python3 -c "import time; t = time.process_time()\nwhile time.process_time() - t < 1.2: pass"'
)


def _policy(tmp_path: Path) -> SandboxPolicy:
    return SandboxPolicy(
        workspace_root=tmp_path,
        use_kernel_sandbox=False,
        allow_unsandboxed=True,
        limits={"cpu": 2},
        timeout_seconds=30,
    )


async def test_kill_nine_beside_cpu_burners_is_not_a_cpu_hit(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    killer = "sleep 3; kill -9 $$"
    (_, _), (_, _), (rc, out) = await asyncio.gather(
        policy.execute_bash_with_code(BURN),
        policy.execute_bash_with_code(BURN),
        policy.execute_bash_with_code(killer),
    )
    assert rc != 0
    assert "limit hit" not in out, out


async def test_real_cpu_hit_is_still_named_while_others_run(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    spinner = "while :; do :; done"
    (_, _), (rc, out) = await asyncio.gather(
        policy.execute_bash_with_code("sleep 1"),
        policy.execute_bash_with_code(spinner),
    )
    assert rc != 0
    assert out.strip().splitlines()[-1].startswith("[limit hit: cpu 2s] Instead:"), out
