"""The session store in the workspace is hidden from `bash` and `edit` (AD-55; gap hunt, ask task:
qwen3.5:9b read its own turns and inbox from a `TETHER_DB` in the workspace)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tether import SandboxPolicy
from tether import sandbox as sb_mod
from tether.sandbox import SandboxViolationError


def _policy(ws: Path, db: Path) -> SandboxPolicy:
    p = SandboxPolicy(workspace_root=ws, use_kernel_sandbox=False)
    p.protect_store(db)
    return p


@pytest.mark.parametrize(
    "cmd",
    ["python3 -c \"import sqlite3; sqlite3.connect('t.db')\"", "cat ./t.db-wal", "ls; cp t.db x"],
)
def test_commands_naming_the_store_are_refused(cmd: str, tmp_path: Path) -> None:
    with pytest.raises(SandboxViolationError, match="session store `t.db`"):
        _policy(tmp_path, tmp_path / "t.db").validate_bash_command(cmd)


def test_similar_names_and_other_files_pass(tmp_path: Path) -> None:
    p = _policy(tmp_path, tmp_path / "t.db")
    for cmd in ("cat test.db", "ls my-t.db.bak", "cat notes.md"):
        p.validate_bash_command(cmd)
    p.resolve_safe_path("test.db")


def test_edit_cannot_open_the_store_or_its_wal(tmp_path: Path) -> None:
    p = _policy(tmp_path, tmp_path / "t.db")
    for name in ("t.db", "t.db-wal", "./t.db-shm"):
        with pytest.raises(SandboxViolationError, match="session store"):
            p.resolve_safe_path(name)


def test_a_store_outside_the_workspace_or_in_dot_tether_changes_nothing(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    for db in (tmp_path / "t.db", ws / ".tether" / "tether.db"):
        p = _policy(ws, db)
        assert p._store == ()
        p.validate_bash_command("cat t.db tether.db")


def test_bwrap_masks_the_store_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "t.db").write_bytes(b"x")
    (tmp_path / "t.db-wal").write_bytes(b"x")
    p = _policy(tmp_path, tmp_path / "t.db")
    monkeypatch.setattr(sb_mod, "_empty_mask_file", lambda: "/empty")
    args = p._protected_mounts()
    assert str(tmp_path / "t.db") in args and str(tmp_path / "t.db-wal") in args
    assert str(tmp_path / "t.db-shm") not in args  # only files that exist
