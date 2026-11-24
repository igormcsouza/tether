"""Fail closed without bwrap (#124 item 2). Scripted: the proxy plays the model, tether is real.

bwrap is hidden by running the CLI with a PATH that holds no `bwrap` binary. Where the kernel has
Landlock, tether jails `bash` with it instead (AD-35), so the fail-closed cases cannot happen there
(the unit tests cover them) and the Landlock case runs instead.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from e2e.conftest import Tether
from tether import landlock

no_landlock = pytest.mark.skipif(landlock.abi() > 0, reason="Landlock jails instead (AD-35)")

NOTICE = "[sandbox] bwrap not available, running with command checks only"


def _no_bwrap(tether: Tether, tmp_path: Path, **extra: str) -> dict[str, str]:
    empty = tmp_path / "nobwrap-bin"
    empty.mkdir(exist_ok=True)
    tether.env.pop("TETHER_SANDBOX", None)
    return {"PATH": str(empty), **extra}


def _run(tether: Tether, env: dict[str, str], *flags: str):
    return tether.cli("run", "--json", "--model", f"e2e/{tether.model}", *flags, "g", env=env)


@no_landlock
def test_write_session_refused_before_any_model_call(tether: Tether, chaos, tmp_path) -> None:
    chaos.script(("done", "x"))
    p = _run(tether, _no_bwrap(tether, tmp_path))
    assert p.returncode == 1, p.stderr
    for hint in ("--allow-unsandboxed", "TETHER_SANDBOX=container", "bubblewrap"):
        assert hint in p.stderr, p.stderr
    assert chaos.requests == [], "a refused session must not reach the model"


@no_landlock
def test_opt_out_runs_with_one_notice_and_status_line(tether: Tether, chaos, tmp_path) -> None:
    chaos.script(("done", "ok"))
    env = _no_bwrap(tether, tmp_path)
    p = _run(tether, env, "--allow-unsandboxed")
    assert p.returncode == 0, p.stderr
    assert p.stderr.count(NOTICE) == 1, p.stderr
    sid = json.loads(p.stdout.strip().splitlines()[-1])["id"]
    st = tether.cli("status", sid, env=env)
    assert "sandbox: command checks only" in st.stdout, st.stdout


def test_read_only_and_container_are_unaffected(tether: Tether, chaos, tmp_path) -> None:
    chaos.script(("done", "ok"), ("done", "ok"))
    ro = _run(tether, _no_bwrap(tether, tmp_path), "--sandbox", "read-only")
    box = _run(tether, _no_bwrap(tether, tmp_path, TETHER_SANDBOX="container"))
    for p in (ro, box):
        assert p.returncode == 0 and NOTICE not in p.stderr, p.stderr


@pytest.mark.skipif(landlock.abi() == 0, reason="kernel has no Landlock")
def test_without_bwrap_landlock_jails_the_session(tether: Tether, chaos, tmp_path) -> None:
    chaos.script("bash touch made.txt", ("done", "ok"))
    env = _no_bwrap(tether, tmp_path)
    for tool in ("bash", "touch"):  # a PATH with the tools the command needs, still no bwrap
        (Path(env["PATH"]) / tool).symlink_to(shutil.which(tool) or tool)
    p = _run(tether, env, "--tools", "bash")
    assert p.returncode == 0 and NOTICE not in p.stderr, p.stderr
    assert (tether.ws / "made.txt").exists()
    sid = json.loads(p.stdout.strip().splitlines()[-1])["id"]
    assert "sandbox: landlock" in tether.cli("status", sid, env=env).stdout
