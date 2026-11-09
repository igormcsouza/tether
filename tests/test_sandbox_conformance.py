"""Sandbox conformance table, shared by the text layer (here) and the bwrap layer (e2e).

Add a row as one line. `expect` is one of:
- "run": validates in both layers and exits 0 under bwrap.
- "refuse": refused by the always-on text rules in both layers.
- "mount": refused by the text rules in the fallback only; bwrap's mounts contain it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy, SandboxViolationError

RUN, REFUSE, MOUNT = "run", "refuse", "mount"
EXPECTS = {RUN, REFUSE, MOUNT}

TABLE: list[tuple[str, str]] = [
    ("ls -la", RUN),
    ("cat README.md", RUN),
    ("grep -rn TODO .", RUN),
    ("sed -i 's/a/b/' notes.txt", RUN),
    ("find . -name '*.txt' -exec wc -l {} +", RUN),
    ("git status", RUN),
    ("git diff", RUN),
    ("git log --oneline", RUN),
    ("python3 -c 'print(1)'", RUN),
    ("uv --version", RUN),
    ("pytest --version", RUN),
    ("node --version", RUN),
    ("make -n", RUN),
    ("curl --version", RUN),
    ("awk '{print $1}' notes.txt", RUN),
    ("head -n 1 notes.txt", RUN),
    ("tail -n 1 notes.txt", RUN),
    ("wc -l notes.txt", RUN),
    ("echo x > out.txt", RUN),
    ("mkdir -p a/b/c", RUN),
    ("git -C {ws}/sub log --oneline", RUN),
    ("sudo ls", REFUSE),
    ("rm -rf /", REFUSE),
    ("dd if=/dev/zero of=disk.img", REFUSE),
    ("mkfs.ext4 disk.img", REFUSE),
    ("chmod 777 /", REFUSE),
    ("cat ~/.ssh/id_rsa", REFUSE),
    ("cat /etc/shadow", REFUSE),
    ("echo x > ../escape.txt", MOUNT),
    ("echo x > .git/config", MOUNT),
    ("echo x > .git/hooks/pre-commit", MOUNT),
    ("echo x > .tether/x.db", MOUNT),
    ("cat .env", MOUNT),
]

# DoD-1 stems: the table must keep at least these commands (prefix match).
RUN_STEMS = (
    "ls",
    "cat",
    "grep -rn",
    "sed -i",
    "find . -name",
    "git status",
    "git diff",
    "git log",
    "python3 -c",
    "uv --version",
    "pytest --version",
    "node --version",
    "make -n",
    "curl --version",
    "awk",
    "head",
    "tail",
    "wc -l",
    "echo x >",
    "mkdir -p",
)
REFUSE_STEMS = (
    "sudo",
    "rm -rf /",
    "dd if=",
    "mkfs",
    "chmod 777",
    "cat ~/.ssh/id_rsa",
    "cat /etc/shadow",
    "echo x > ../escape.txt",
    "echo x > .git/config",
    "echo x > .git/hooks",
    "echo x > .tether/",
    "cat .env",
)

# Item 1 of #124: these must validate once bwrap is the enforcer.
ACCEPT_KERNEL = ("ls ~/..", "cat .env.example", "git -C {ws}/sub log")


def _line(cmd: str, ws: Path) -> str:
    # str.replace, not str.format: rows contain braces such as `{}` and `{print}`.
    return cmd.replace("{ws}", str(ws))


def test_table_sizes() -> None:
    runs = [c for c, e in TABLE if e == RUN]
    others = [c for c, e in TABLE if e != RUN]
    assert len(runs) >= 20, f"need >=20 must-run rows, have {len(runs)}"
    assert len(others) >= 12, f"need >=12 must-refuse rows, have {len(others)}"
    assert {e for _, e in TABLE} <= EXPECTS, "unknown expect value in TABLE"
    commands = [c for c, _ in TABLE]
    assert len(commands) == len(set(commands)), "duplicate command rows"
    for stem in RUN_STEMS:
        assert any(c.startswith(stem) for c in runs), f"no must-run row for {stem!r}"
    for stem in REFUSE_STEMS:
        assert any(c.startswith(stem) for c in others), f"no must-refuse row for {stem!r}"


@pytest.mark.parametrize(("cmd", "expect"), TABLE, ids=[c for c, _ in TABLE])
def test_text_layer_matches_table(cmd: str, expect: str, tmp_path: Path) -> None:
    policy = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    line = _line(cmd, tmp_path)
    if expect == RUN:
        policy.validate_bash_command(line)
        return
    with pytest.raises(SandboxViolationError) as exc:
        policy.validate_bash_command(line)
    assert "Instead:" in str(exc.value), str(exc.value)


def test_text_layer_refuses_home_parent_without_kernel(tmp_path: Path) -> None:
    # ACCEPT_KERNEL's `ls ~/..` is only allowed under bwrap; the text layer must refuse it.
    policy = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    with pytest.raises(SandboxViolationError) as exc:
        policy.validate_bash_command("ls ~/..")
    assert "Instead:" in str(exc.value), str(exc.value)


def test_kernel_mode_skips_mount_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Item 1 of #124 as a CI proxy: with bwrap active, the mount-enforced text rules do not fire.
    monkeypatch.setattr(sb_mod, "_BWRAP_USABLE", True)
    policy = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=True)
    for cmd in ACCEPT_KERNEL:
        policy.validate_bash_command(_line(cmd, tmp_path))
    for cmd, expect in TABLE:
        line = _line(cmd, tmp_path)
        if expect == REFUSE:
            with pytest.raises(SandboxViolationError):
                policy.validate_bash_command(line)
        else:
            policy.validate_bash_command(line)
