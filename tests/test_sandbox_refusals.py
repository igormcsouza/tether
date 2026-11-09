"""Sandbox refusals name the rule, what to do instead, and the flag that would permit it (#124)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

import tether.sandbox as sb_mod
from tether import SandboxPolicy, SandboxViolationError

_MSG_RE = re.compile(r"^Sandbox violation: (.+?)\. Instead: (.+?)\.(?: Flag: .+)?$")
_LONG_WORKSPACE = "/" + "/".join("x" * 51 for _ in range(4))  # 208 chars
_LONG_PATH = "p" * 400

# Expected (rule fragment, alternative fragment) per trigger: every refusal must name both.
_EXPECT: dict[str, tuple[str, str]] = {
    "read_only_write": ("file writes are disabled", "read the file"),
    "outside_workspace": ("resolves outside workspace", "inside the workspace"),
    "protected_env": ("protected path `.env`", "`.env.example`"),
    "env_file": ("protected path `.env`", "`.env.example`"),
    "git_config": ("protected path `.git/config`", "outside the session"),
    "tether_store": ("protected path `.tether/x`", "outside `.tether/`"),
    "key_file": ("protected path `keys/server.pem`", "outside the workspace"),
    "empty_command": ("Empty command", "non-empty"),
    "sudo": ("`sudo`", "without elevated privileges"),
    "user_switch": ("user switching", "current user"),
    "rm_rf_root": ("`rm -rf /`", "inside the workspace"),
    "dd": ("`dd`", "head -c"),
    "mkfs": ("disk utilities", "workspace files"),
    "disk_utility": ("disk utilities", "workspace files"),
    "chmod_777": ("`chmod 777`", "chmod 755"),
    "fork_bomb": ("fork bombs", "non-destructive"),
    "ssh_keys": ("system secrets", "workspace paths"),
    "parent_traversal": ("parent directory traversal", "inside the workspace"),
    "absolute_outside": ("absolute path `/etc/hosts`", "inside the workspace"),
    "read_only_mutating": ("mutating shell commands", "inspect-only"),
    "read_only_binary": ("`python3`", "allowlisted"),
}
_NAMES = tuple(_EXPECT)


def _triggers(tmp_path: Path) -> dict[str, Callable[[], object]]:
    """One input per raise site in tether/sandbox.py (text rules run with the kernel off)."""
    ws = SandboxPolicy(profile="workspace-write", workspace_root=tmp_path, use_kernel_sandbox=False)
    ro = SandboxPolicy(profile="read-only", workspace_root=tmp_path, use_kernel_sandbox=False)
    return {
        "read_only_write": lambda: ro.resolve_safe_path("notes.txt", write=True),
        "outside_workspace": lambda: ws.resolve_safe_path("../outside.txt", write=True),
        "protected_env": lambda: ws.resolve_safe_path(".env"),
        "env_file": lambda: ws.validate_bash_command("cat .env"),
        "git_config": lambda: ws.resolve_safe_path(".git/config"),
        "tether_store": lambda: ws.resolve_safe_path(".tether/x"),
        "key_file": lambda: ws.resolve_safe_path("keys/server.pem"),
        "empty_command": lambda: ws.validate_bash_command("   "),
        "sudo": lambda: ws.validate_bash_command("sudo ls"),
        "user_switch": lambda: ws.validate_bash_command("su root"),
        "rm_rf_root": lambda: ws.validate_bash_command("rm -rf /"),
        "dd": lambda: ws.validate_bash_command("dd if=/dev/zero of=x bs=1M"),
        "mkfs": lambda: ws.validate_bash_command("mkfs.ext4 /dev/sdb1"),
        "disk_utility": lambda: ws.validate_bash_command("fdisk -l"),
        "chmod_777": lambda: ws.validate_bash_command("chmod 777 f.txt"),
        "fork_bomb": lambda: ws.validate_bash_command(":(){ :|:& };:"),
        "ssh_keys": lambda: ws.validate_bash_command("cat ~/.ssh/id_rsa"),
        "parent_traversal": lambda: ws.validate_bash_command("ls ../"),
        "absolute_outside": lambda: ws.validate_bash_command("cat /etc/hosts"),
        "read_only_mutating": lambda: ro.validate_bash_command("echo hi > out.txt"),
        "read_only_binary": lambda: ro.validate_bash_command("python3 x.py"),
    }


def _refusal_text(fn: Callable[[], object]) -> str:
    with pytest.raises(SandboxViolationError) as info:
        fn()
    return str(info.value)


def _parts(msg: str) -> tuple[str, str]:
    match = _MSG_RE.match(msg)
    assert match, msg
    return match.group(1), match.group(2)


@pytest.mark.parametrize("name", _NAMES)
def test_every_refusal_has_non_empty_rule_and_instead(tmp_path: Path, name: str) -> None:
    rule, instead = _parts(_refusal_text(_triggers(tmp_path)[name]))
    assert rule.strip(), name
    assert instead.strip(), name


@pytest.mark.parametrize("name", _NAMES)
def test_refusal_names_expected_reason_and_alternative(tmp_path: Path, name: str) -> None:
    msg = _refusal_text(_triggers(tmp_path)[name])
    rule, instead = _parts(msg)
    want_rule, want_instead = _EXPECT[name]
    assert want_rule in rule, msg
    assert want_instead in instead, msg


def test_network_refusal_without_bwrap_has_rule_instead_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sb_mod, "_can_use_bwrap", lambda: False)
    policy = SandboxPolicy(workspace_root=tmp_path, network=False, use_kernel_sandbox=True)
    msg = _refusal_text(lambda: policy._build_exec_argv("echo hi"))
    rule, instead = _parts(msg)
    assert rule.strip(), msg
    assert "--no-network" in instead, msg
    assert len(msg) < 300, msg


def test_message_content_by_rule(tmp_path: Path) -> None:
    triggers = _triggers(tmp_path)

    outside = _refusal_text(triggers["outside_workspace"])
    assert "inside the workspace" in outside, outside
    assert str(tmp_path) not in outside, outside

    protected = _refusal_text(triggers["protected_env"])
    assert "protected" in protected, protected
    assert "not accessible" in protected, protected
    assert "not writable" not in protected, protected

    ws = SandboxPolicy(workspace_root=tmp_path, use_kernel_sandbox=False)
    write_refusal = _refusal_text(lambda: ws.resolve_safe_path(".env", write=True))
    assert "not writable" in write_refusal, write_refusal

    rm_root = _refusal_text(triggers["rm_rf_root"])
    assert "Instead:" in rm_root, rm_root


def test_flag_hint_where_one_exists(tmp_path: Path) -> None:
    triggers = _triggers(tmp_path)
    for name in ("read_only_write", "read_only_mutating", "read_only_binary"):
        msg = _refusal_text(triggers[name])
        assert "--sandbox workspace-write" in msg, (name, msg)


def test_messages_are_short(tmp_path: Path) -> None:
    triggers = _triggers(tmp_path)
    for name in _NAMES:
        msg = _refusal_text(triggers[name])
        assert len(msg) < 300, (name, len(msg), msg)


def test_long_workspace_and_long_path_stay_short(tmp_path: Path) -> None:
    assert len(_LONG_WORKSPACE) == 208
    long_ws = SandboxPolicy(workspace_root=Path(_LONG_WORKSPACE), use_kernel_sandbox=False)
    cases = [
        lambda: long_ws.resolve_safe_path("/" + _LONG_PATH, write=True),
        lambda: long_ws.resolve_safe_path(_LONG_PATH + ".pem"),
        lambda: long_ws.validate_bash_command("cat /" + _LONG_PATH),
    ]
    for fn in cases:
        msg = _refusal_text(fn)
        assert len(msg) < 300, msg
        assert _LONG_WORKSPACE not in msg, msg
        assert _LONG_PATH not in msg, msg
