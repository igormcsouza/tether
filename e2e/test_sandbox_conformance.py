"""Sandbox conformance under the real bwrap jail (#124 items 1 and 9).

Uses the same TABLE as tests/test_sandbox_conformance.py. Skipped when bwrap cannot create user
namespaces. Runs in-process, with no model and no CLI.
"""

from __future__ import annotations

import resource
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import tether.sandbox as sb_mod
from tests.test_sandbox_conformance import MOUNT, REFUSE, RUN, TABLE, _line
from tether import SandboxPolicy, SandboxViolationError

pytestmark = pytest.mark.skipif(
    not sb_mod._can_use_bwrap(),
    reason="bwrap missing or unusable (no user namespaces): kernel conformance not run",
)

SENTINEL = "SENTINEL-SECRET-7f3a"


def _fsize_limit() -> None:
    # Bypassed rows may really write: cap any single file at 1 MiB.
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))


PROBE = "conformance-probe.txt"
# Only the e2e layer runs this row: the text layer cannot see a write into the home directory.
HOME_ROW = ("echo x > " + "~" + "/conformance-probe.txt", MOUNT)
E2E_ROWS = [*TABLE, HOME_ROW]


@pytest.fixture
def home_probe() -> Iterator[Path]:
    # A leak would create this file in the real home. Never delete a file this run did not make.
    probe = Path.home() / PROBE
    assert not probe.exists(), f"{probe} is left over from an earlier run: remove it first"
    yield probe
    probe.unlink(missing_ok=True)


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    root = tmp_path / "ws"
    (root / ".tether").mkdir(parents=True)
    (root / "README.md").write_text("TODO: write docs\n")
    (root / "notes.txt").write_text("a b\nc d\n")
    (root / "Makefile").write_text("all:\n\techo ok\n")
    (root / ".env").write_text(f"{SENTINEL}=1\n")
    (root / ".env.example").write_text("KEY=\n")
    for repo in (root, root / "sub"):
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                "init",
            ],
            check=True,
        )
    return root


def _snapshot(ws: Path) -> dict[str, Any]:
    """Host-side state a refused command must not change."""

    def listing(d: Path) -> list[str]:
        if not d.exists():
            return []
        return sorted(str(p.relative_to(d)) for p in d.rglob("*"))

    return {
        "git_config": (ws / ".git" / "config").read_bytes(),
        "env": (ws / ".env").read_bytes(),
        "hooks": listing(ws / ".git" / "hooks"),
        "tether": listing(ws / ".tether"),
        "parent": sorted(p.name for p in ws.parent.iterdir()),
    }


@pytest.mark.parametrize(("cmd", "expect"), E2E_ROWS, ids=[c for c, _ in E2E_ROWS])
async def test_kernel_layer_matches_table(
    cmd: str, expect: str, ws: Path, home_probe: Path
) -> None:
    line = _line(cmd, ws)
    first = line.split()[0]
    if expect == RUN and shutil.which(first) is None:
        pytest.skip(f"{first} not on the sandbox PATH")
    before = _snapshot(ws)
    policy = SandboxPolicy(workspace_root=ws)
    if expect == RUN:
        rc, out = await policy.execute_bash_with_code(line)
        assert rc == 0, f"{line!r} should run under bwrap, got rc {rc}: {out}"
        return
    try:
        _, out = await policy.execute_bash_with_code(line)
    except SandboxViolationError:
        out = ""
    assert SENTINEL not in out, f"{line!r} leaked the masked secret: {out}"
    assert _snapshot(ws) == before, f"{line!r} changed host state"
    assert not home_probe.exists(), f"{line!r} wrote the real home"


REFUSE_ROWS = [c for c, e in TABLE if e == REFUSE]
# Destructive commands are never run with the text rules off; the text layer test covers them.
DESTRUCTIVE = {"rm", "chmod", "dd", "mkfs"}
KERNEL_REFUSE_ROWS = [c for c in REFUSE_ROWS if c.split()[0] not in DESTRUCTIVE]


@pytest.mark.parametrize("cmd", KERNEL_REFUSE_ROWS, ids=KERNEL_REFUSE_ROWS)
def test_kernel_refuse_rows_do_not_leak(cmd: str, ws: Path, home_probe: Path) -> None:
    # Bypasses the text rules on purpose: bwrap alone must keep the secret and the host intact.
    # A non-zero exit is fine (missing program, or blocked by the kernel).
    line = _line(cmd, ws)
    before = _snapshot(ws)
    argv = SandboxPolicy(workspace_root=ws)._build_exec_argv(line)
    proc = subprocess.run(
        argv,
        preexec_fn=_fsize_limit,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=ws,
    )
    out = proc.stdout + proc.stderr
    assert SENTINEL not in out, f"{line!r} leaked the masked secret: {out}"
    assert _snapshot(ws) == before, f"{line!r} changed host state"
    assert not home_probe.exists(), f"{line!r} wrote the real home"


async def test_kernel_first_acceptance(ws: Path) -> None:
    policy = SandboxPolicy(workspace_root=ws)
    rc, out = await policy.execute_bash_with_code("ls ~/..")
    assert rc == 0, out
    rc, out = await policy.execute_bash_with_code("cat .env.example")
    assert rc == 0 and "KEY=" in out, out
    rc, out = await policy.execute_bash_with_code(f"git -C {ws}/sub log")
    assert rc == 0, out
    # A masked .env reads as empty (the output is "[exit 0: no output]"), never the secret.
    rc, out = await policy.execute_bash_with_code("cat .env")
    assert rc == 0 and SENTINEL not in out, out
    assert out.strip() == "" or out.startswith("[exit 0: no output]"), out
