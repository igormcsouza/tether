"""Landlock jail (AD-35): a write to the host /tmp is refused, and the output says where to write.

Scripted: the proxy plays the model, tether is real. bwrap is hidden with a PATH that holds no
`bwrap` binary, so `bash` runs under Landlock, as in `test_sandbox_fail_closed.py`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from e2e.conftest import Tether
from tether import landlock

HINT = "[sandbox] /tmp is not writable here: write scratch files to $TMPDIR"


@pytest.mark.skipif(landlock.abi() == 0, reason="kernel has no Landlock")
def test_landlock_refused_tmp_write_gets_the_hint_and_tmpdir_works(
    tether: Tether, chaos, tmp_path: Path
) -> None:
    chaos.script(
        "bash echo hi > /tmp/tether_e2e_probe",
        "bash echo hi > $TMPDIR/p && cat $TMPDIR/p",
        ("done", "ok"),
    )
    empty = tmp_path / "nobwrap-bin"
    empty.mkdir(exist_ok=True)
    tether.env.pop("TETHER_SANDBOX", None)
    env = {"PATH": str(empty)}
    for tool in ("bash", "echo", "cat"):  # the tools the commands need, still no bwrap
        (empty / tool).symlink_to(shutil.which(tool) or tool)
    p = tether.cli(
        "run", "--json", "--model", f"e2e/{tether.model}", "--tools", "bash", "g", env=env
    )
    assert p.returncode == 0, p.stderr
    sid = json.loads(p.stdout.strip().splitlines()[-1])["id"]
    refused, works = tether.tool_outputs(sid)[:2]
    assert refused.count(HINT) == 1, refused
    assert works.splitlines()[0] == "hi", works
    assert HINT not in works
