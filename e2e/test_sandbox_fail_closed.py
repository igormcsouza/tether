"""Fail closed without bwrap (#124 item 2). Scripted: the proxy plays the model, tether is real.

bwrap is hidden by running the CLI with a PATH that holds no `bwrap` binary.
"""

from __future__ import annotations

import json
from pathlib import Path

from e2e.conftest import Tether

NOTICE = "[sandbox] bwrap not available, running with command checks only"


def _no_bwrap(tether: Tether, tmp_path: Path, **extra: str) -> dict[str, str]:
    empty = tmp_path / "nobwrap-bin"
    empty.mkdir(exist_ok=True)
    tether.env.pop("TETHER_SANDBOX", None)
    return {"PATH": str(empty), **extra}


def _run(tether: Tether, env: dict[str, str], *flags: str):
    return tether.cli("run", "--json", "--model", f"e2e/{tether.model}", *flags, "g", env=env)


def test_write_session_refused_before_any_model_call(tether: Tether, chaos, tmp_path) -> None:
    chaos.script(("done", "x"))
    p = _run(tether, _no_bwrap(tether, tmp_path))
    assert p.returncode == 1, p.stderr
    for hint in ("--allow-unsandboxed", "TETHER_SANDBOX=container", "bubblewrap"):
        assert hint in p.stderr, p.stderr
    assert chaos.requests == [], "a refused session must not reach the model"


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
