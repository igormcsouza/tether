"""Deterministic security sandbox for Tether (workspace jail, env scrubbing, Linux bwrap)."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SandboxViolationError(PermissionError):
    """Raised when a tool call violates the deterministic SandboxPolicy."""


_SENSITIVE_FILENAMES = {
    ".env",
    ".git/config",
    ".git/hooks",
    ".tether",
    "id_rsa",
    "id_ed25519",
    "authorized_keys",
}

_SECRET_ENV_RE = re.compile(
    r"(API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE_KEY|^AWS_|^OPENAI_|^ANTHROPIC_|^GH_"
    r"|^SSH_AUTH_SOCK$|^GPG_AGENT_INFO$)",
    re.IGNORECASE,
)

_BLOCKED_BASH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:^|[;&|()\s])sudo\b"), "`sudo` privilege escalation is blocked"),
    (re.compile(r"(?:^|[;&|()\s])su\b"), "`su` user switching is blocked"),
    (
        re.compile(r"(?:^|[;&|()\s])(?:mkfs|fdisk|parted|mount|umount)\b"),
        "disk utilities are blocked",
    ),
    (re.compile(r"(?:^|[;&|()\s])dd\s+if="), "`dd` raw block operations are blocked"),
    (re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+/(?:\s|$|\*)"), "`rm -rf /` is blocked"),
    (re.compile(r"chmod\s+(?:-R\s+)?777\b"), "`chmod 777` is blocked"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"), "fork bombs are blocked"),
    (
        re.compile(r"(?:^|[\s/\"'])(\.env(?:\.[a-zA-Z0-9_-]+)?)\b"),
        "access to `.env` files is blocked",
    ),
    (
        re.compile(r"(?:^|[\s/\"'])\.tether(?:/|\b)"),
        "access to `.tether` internal store is blocked",
    ),
    (
        re.compile(r"(?:^|[\s/\"'])\.git/(?:config|hooks)\b"),
        "access to `.git/config` or `hooks` is blocked",
    ),
    (
        re.compile(r"(?:~|\$HOME)/\.ssh\b|/etc/(?:shadow|sudoers)\b"),
        "access to system secrets is blocked",
    ),
]

_READONLY_ALLOWED_BINARIES = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "rg",
    "find",
    "wc",
    "pwd",
    "echo",
    "stat",
    "file",
    "which",
    "uname",
    "date",
    "sort",
    "uniq",
    "cut",
    "tr",
}

_BWRAP_USABLE: bool | None = None


def _can_use_bwrap() -> bool:
    """Probe once whether `bwrap` is installed and permitted by host kernel namespaces."""
    global _BWRAP_USABLE
    if _BWRAP_USABLE is not None:
        return _BWRAP_USABLE

    bwrap_bin = shutil.which("bwrap")
    if not bwrap_bin:
        _BWRAP_USABLE = False
        return False

    try:
        proc = subprocess.run(
            [bwrap_bin, "--ro-bind", "/", "/", "--unshare-all", "--", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
        _BWRAP_USABLE = proc.returncode == 0
    except Exception:
        _BWRAP_USABLE = False
    return _BWRAP_USABLE


@dataclass(slots=True)
class SandboxPolicy:
    """Deterministic security envelope enforced by the harness (never by the LLM)."""

    profile: str = "workspace-write"  # "workspace-write" | "read-only"
    workspace_root: Path = field(default_factory=lambda: Path.cwd().resolve())
    timeout_seconds: float = 30.0
    max_output_chars: int = 12000
    use_kernel_sandbox: bool = True
    verify_commands: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()
        if self.profile not in ("workspace-write", "read-only"):
            raise ValueError(f"Unsupported sandbox profile: {self.profile}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "workspace_root": str(self.workspace_root),
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
            "use_kernel_sandbox": self.use_kernel_sandbox,
            "verify_commands": list(self.verify_commands),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SandboxPolicy:
        if not data:
            return cls()
        raw_verify = data.get("verify_commands") or []
        return cls(
            profile=str(data.get("profile", "workspace-write")),
            workspace_root=Path(str(data.get("workspace_root", Path.cwd()))).resolve(),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
            max_output_chars=int(data.get("max_output_chars", 12000)),
            use_kernel_sandbox=bool(data.get("use_kernel_sandbox", True)),
            verify_commands=[str(v) for v in raw_verify if str(v).strip()],
        )

    def attenuate(self, child_profile: str | None = None) -> SandboxPolicy:
        """Create a child SandboxPolicy that can only narrow (never escalate) privileges."""
        if self.profile == "read-only":
            effective_profile = "read-only"
        else:
            effective_profile = child_profile if child_profile == "read-only" else self.profile

        return SandboxPolicy(
            profile=effective_profile,
            workspace_root=self.workspace_root,
            timeout_seconds=self.timeout_seconds,
            max_output_chars=self.max_output_chars,
            use_kernel_sandbox=self.use_kernel_sandbox,
            verify_commands=list(self.verify_commands),
        )

    def resolve_safe_path(self, raw_path: str | Path, *, write: bool = False) -> Path:
        """Resolve a path and enforce workspace confinement + sensitive-file protection."""
        if write and self.profile == "read-only":
            raise SandboxViolationError(
                "Sandbox violation: file writes are disabled in `read-only` profile."
            )

        p = Path(raw_path)
        candidate = (self.workspace_root / p).resolve() if not p.is_absolute() else p.resolve()

        if not candidate.is_relative_to(self.workspace_root):
            raise SandboxViolationError(
                f"Sandbox violation: path `{raw_path}` resolves outside "
                f"workspace `{self.workspace_root}`."
            )

        rel = candidate.relative_to(self.workspace_root)
        rel_str = rel.as_posix()
        parts = rel.parts

        # Check sensitive patterns
        if (
            rel_str in _SENSITIVE_FILENAMES
            or any(part.startswith(".env") for part in parts)
            or ".tether" in parts
            or (len(parts) >= 2 and parts[0] == ".git" and parts[1] in ("config", "hooks"))
            or candidate.name in ("id_rsa", "id_ed25519", "authorized_keys")
            or candidate.suffix in (".pem", ".key")
        ):
            raise SandboxViolationError(
                f"Sandbox violation: access to protected path `{rel_str}` is denied."
            )

        return candidate

    def scrub_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Return a sanitized environment dictionary with secrets stripped."""
        source = base_env if base_env is not None else dict(os.environ)
        clean: dict[str, str] = {}
        for k, v in source.items():
            if _SECRET_ENV_RE.search(k):
                continue
            clean[k] = v
        clean["HOME"] = str(self.workspace_root)
        clean["PWD"] = str(self.workspace_root)
        clean["PAGER"] = "cat"
        return clean

    def validate_bash_command(self, cmd: str) -> None:
        """Deterministically validate a shell command against sandbox rules."""
        stripped = cmd.strip()
        if not stripped:
            raise SandboxViolationError("Empty command.")

        for pattern, reason in _BLOCKED_BASH_PATTERNS:
            if pattern.search(stripped):
                raise SandboxViolationError(f"Sandbox violation: {reason}.")

        # Block explicit parent directory traversal (`..`) or absolute paths outside workspace
        try:
            tokens = shlex.split(stripped, posix=True)
        except ValueError:
            tokens = stripped.split()

        for tok in tokens:
            if tok == ".." or tok.startswith("../") or "/../" in tok or tok.endswith("/.."):
                raise SandboxViolationError(
                    "Sandbox violation: parent directory traversal (`..`) is blocked."
                )
            if tok.startswith("/") and not tok.startswith(("/dev/null", "/tmp")):
                resolved = Path(tok).resolve()
                if not resolved.is_relative_to(self.workspace_root):
                    raise SandboxViolationError(
                        f"Sandbox violation: absolute path `{tok}` is outside workspace."
                    )

        if self.profile == "read-only":
            if any(
                op in stripped
                for op in (">", ">>", "| tee", "rm ", "mv ", "cp ", "mkdir ", "touch ")
            ):
                raise SandboxViolationError(
                    "Sandbox violation: mutating shell commands are blocked in `read-only` profile."
                )
            first_bin = Path(tokens[0]).name if tokens else ""
            if first_bin not in _READONLY_ALLOWED_BINARIES:
                raise SandboxViolationError(
                    f"Sandbox violation: binary `{first_bin}` is not in the `read-only` allowlist."
                )

    def _protected_mounts(self) -> list[str]:
        """bwrap args masking sensitive workspace paths so globs/indirection cannot reach them."""
        ws = self.workspace_root
        args: list[str] = []
        for env_file in sorted(ws.glob(".env*")):
            if env_file.is_file():
                args += ["--ro-bind", "/dev/null", str(env_file)]
        for hidden in (ws / ".tether", ws / ".git" / "hooks"):
            if hidden.is_dir():
                args += ["--tmpfs", str(hidden)]
        git_config = ws / ".git" / "config"
        if git_config.is_file():
            args += ["--ro-bind", "/dev/null", str(git_config)]
        return args

    def _build_exec_argv(self, cmd: str) -> list[str]:
        """Wrap command in Linux `bwrap` kernel sandbox if available, else standard bash."""
        if self.use_kernel_sandbox and _can_use_bwrap():
            ws = str(self.workspace_root)
            bwrap_cmd = [
                "bwrap",
                "--ro-bind",
                "/",
                "/",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--tmpfs",
                os.path.expanduser("~"),
                *(["--tmpfs", "/run/user"] if os.path.isdir("/run/user") else []),
                "--bind" if self.profile == "workspace-write" else "--ro-bind",
                ws,
                ws,
                *self._protected_mounts(),
                "--chdir",
                ws,
                "--unshare-pid",
                "--unshare-ipc",
                "--die-with-parent",
                "--new-session",
                "--",
                "bash",
                "-c",
                cmd,
            ]
            return bwrap_cmd
        return ["bash", "-c", cmd]

    async def execute_bash_with_code(self, cmd: str, stdin: str | None = None) -> tuple[int, str]:
        """Execute a shell command in the deterministic sandbox and return (returncode, output)."""
        effective_cmd = cmd.strip()
        if not effective_cmd and stdin:
            effective_cmd = stdin.strip()
            stdin = None

        self.validate_bash_command(effective_cmd)
        argv = self._build_exec_argv(effective_cmd)
        env = self.scrub_env()

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workspace_root),
            env=env,
            start_new_session=True,
        )

        stdin_bytes = stdin.encode("utf-8") if stdin is not None else None
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
            return (
                124,
                f"Error: command timed out after {self.timeout_seconds:.1f}s (SIGKILL).",
            )

        returncode = int(proc.returncode or 0)
        stdout_str = stdout_b.decode("utf-8", errors="replace")
        stderr_str = stderr_b.decode("utf-8", errors="replace")
        combined = stdout_str
        if stderr_str:
            combined = f"{stdout_str}\n[stderr]\n{stderr_str}".strip()

        if not combined:
            combined = f"[exit {returncode}]"
        elif returncode != 0:
            combined = f"{combined}\n[exit {returncode}]"

        if len(combined) > self.max_output_chars:
            half = self.max_output_chars // 2
            omitted = len(combined) - self.max_output_chars
            combined = (
                f"{combined[:half]}\n"
                f"... [truncated {omitted:,} chars by sandbox cap] ...\n"
                f"{combined[-half:]}"
            )
        return returncode, combined

    async def execute_bash(self, cmd: str, stdin: str | None = None) -> str:
        """Execute a shell command inside the deterministic sandbox."""
        _, combined = await self.execute_bash_with_code(cmd, stdin=stdin)
        return combined
