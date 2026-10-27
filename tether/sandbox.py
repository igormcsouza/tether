"""Deterministic security sandbox for Tether (workspace jail, env scrubbing, Linux bwrap)."""

from __future__ import annotations

import asyncio
import functools
import glob
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

# Env allowlist (Rule 6): only these names reach `bash` subprocesses. Extra names can be passed
# through explicitly with TETHER_ENV_PASSTHROUGH=NAME1,NAME2.
_ENV_ALLOW_EXACT = {
    "PATH", "LANG", "LANGUAGE", "TERM", "COLORTERM", "NO_COLOR", "TZ", "USER", "LOGNAME",
    "SHELL", "TMPDIR", "VIRTUAL_ENV", "CI", "PYTHONPATH", "PYTHONIOENCODING",
}  # fmt: skip
_ENV_ALLOW_PREFIX = ("LC_",)

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
        re.compile(r"(?:~|\$HOME)/\.ssh\b|/etc/(?:shadow|sudoers)\b"),
        "access to system secrets is blocked",
    ),
]

# Text rules that bwrap's mounts already enforce (masked secrets, hidden `.tether/`, read-only root,
# hidden home). They only guard the no-bwrap fallback: with the kernel jail they would just refuse
# harmless commands such as `cat .env.example` (#125).
_MOUNT_ENFORCED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?:^|[\s/\"'])(\.env(?!\.(?:example|sample|template|dist)\b)"
            r"(?:\.[a-zA-Z0-9_-]+)?)\b"
        ),
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

# Binaries whose first non-option argument is a program/pattern (e.g. awk '/re/{...}'), not a path.
_PROGRAM_ARG_BINARIES = {"awk", "gawk", "mawk", "sed", "grep", "egrep", "fgrep", "rg", "perl"}
_CMD_SEPARATORS = {"&&", "||", ";", "|", "&", "|&"}
_REGEX_META_RE = re.compile(r"[{}^$*()|]")

# Secret-looking file names masked at the mount level at any depth under the workspace.
_MASKED_NAME_RE = re.compile(
    r"^(?:\.env(?!.*\.(?:example|sample|template|dist)$)(?:\..*)?|id_rsa|id_ed25519|authorized_keys|.*\.(?:pem|key))$"
)
_MASK_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tether"}
_MASK_MAX_FILES = 200
_MASK_MAX_DEPTH = 8

# Host directories holding other users' data / service sockets, hidden behind empty tmpfs.
_HIDDEN_HOST_DIRS = ("/home", "/media", "/mnt", "/srv", "/var/tmp")
# Never re-exposed even when a PATH entry points into them (credentials and config).
_PRIVATE_DIR_NAMES = frozenset({".ssh", ".gnupg", ".aws", ".kube", ".docker", ".config", ".netrc"})
_MAX_PATH_MOUNTS = 16

_BWRAP_USABLE: bool | None = None


@functools.lru_cache(maxsize=1)
def _host_socket_masks() -> tuple[str, ...]:
    """bwrap args hiding host unix sockets (docker.sock, containerd, dbus...) under /run.

    ro-bind does not stop `connect()`, so a reachable docker.sock is a host escape.
    """
    paths = [p for pat in ("/run/*", "/run/*/*") for p in sorted(glob.glob(pat))]
    return tuple(a for p in paths if Path(p).is_socket() for a in ("--ro-bind", "/dev/null", p))


def _is_env_secret(name: str) -> bool:
    """`.env`, `.env.local`, ...; the committed templates (`.env.example`) hold no secrets."""
    return name.startswith(".env") and not name.endswith(
        (".example", ".sample", ".template", ".dist")
    )


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


_RULE_LINE = re.compile(r"^(?:={20,}|-{20,})$\n?", re.M)


def _compact_output(text: str, root: Path) -> str:
    """Token saver: drop `====`/`----` rule lines and the absolute workspace prefix."""
    return _RULE_LINE.sub("", text.replace(f"{root}/", ""))


@dataclass(slots=True)
class SandboxPolicy:
    """Deterministic security envelope enforced by the harness (never by the LLM)."""

    profile: str = "workspace-write"  # "workspace-write" | "read-only"
    workspace_root: Path = field(default_factory=lambda: Path.cwd().resolve())
    timeout_seconds: float = 30.0
    max_output_chars: int = 12000
    use_kernel_sandbox: bool = True
    network: bool = True
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
            "network": self.network,
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
            network=bool(data.get("network", True)),
            verify_commands=[str(v) for v in raw_verify if str(v).strip()],
        )

    def attenuate(
        self, child_profile: str | None = None, child_network: bool | None = None
    ) -> SandboxPolicy:
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
            network=self.network and child_network is not False,
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
            or any(_is_env_secret(part) for part in parts)
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
        """Return a sanitized environment: allowlist only, so unknown secrets never leak."""
        source = base_env if base_env is not None else dict(os.environ)
        extra = {
            n.strip() for n in source.get("TETHER_ENV_PASSTHROUGH", "").split(",") if n.strip()
        }
        clean: dict[str, str] = {}
        for k, v in source.items():
            if k in extra or k in _ENV_ALLOW_EXACT or k.startswith(_ENV_ALLOW_PREFIX):
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

        kernel = self.use_kernel_sandbox and _can_use_bwrap()
        for pattern, reason in (
            _BLOCKED_BASH_PATTERNS if kernel else _BLOCKED_BASH_PATTERNS + _MOUNT_ENFORCED_PATTERNS
        ):
            if pattern.search(stripped):
                raise SandboxViolationError(f"Sandbox violation: {reason}.")

        # Block explicit parent directory traversal (`..`) or absolute paths outside workspace
        try:
            tokens = shlex.split(stripped, posix=True)
        except ValueError:
            tokens = stripped.split()

        cmd_start, cur_bin, pending, prev = True, "", False, ""
        for tok in (
            [] if kernel else tokens
        ):  # the kernel jail enforces paths; text rules are fallback
            if tok in _CMD_SEPARATORS:
                cmd_start = True
                continue
            is_program_arg = False
            if cmd_start:
                cmd_start, cur_bin = False, Path(tok).name
                pending = cur_bin in _PROGRAM_ARG_BINARIES
            elif cur_bin in _PROGRAM_ARG_BINARIES and not tok.startswith("-"):
                # awk/sed/grep program or pattern (e.g. `/^## M/{n++}`) is not a filesystem path;
                # `-f <file>` operands still are.
                is_program_arg = prev not in ("-f", "--file") and (
                    pending or (tok.startswith("/") and bool(_REGEX_META_RE.search(tok)))
                )
                pending = False
            prev = tok
            if is_program_arg:
                continue
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
        """bwrap args masking secret-looking workspace files (any depth) from globs/indirection."""
        ws = self.workspace_root
        args: list[str] = []
        found = 0
        for root, dirs, files in os.walk(ws):
            depth = len(Path(root).relative_to(ws).parts)
            dirs[:] = (
                [d for d in dirs if d not in _MASK_SKIP_DIRS] if depth < _MASK_MAX_DEPTH else []
            )
            for name in files:
                if found < _MASK_MAX_FILES and _MASKED_NAME_RE.match(name):
                    args += ["--ro-bind", "/dev/null", str(Path(root) / name)]
                    found += 1
        for hidden in (ws / ".tether", ws / ".git" / "hooks"):
            if hidden.is_dir():
                args += ["--tmpfs", str(hidden)]
        git_config = ws / ".git" / "config"
        if git_config.is_file():
            args += ["--ro-bind", "/dev/null", str(git_config)]
        return args

    def _venv_prefixes(self) -> list[str]:
        """Interpreter prefixes of the workspace venvs (`home =` in pyvenv.cfg), e.g. a uv-managed
        Python under `~/.local/share/uv`: without it `.venv/bin/pytest` cannot start (#76)."""
        out: list[str] = []
        for name in (".venv", "venv"):
            cfg = self.workspace_root / name / "pyvenv.cfg"
            try:
                text = cfg.read_text()
            except OSError:
                continue
            match = re.search(r"^home\s*=\s*(\S.*)$", text, re.MULTILINE)
            if match:
                home = Path(match.group(1).strip())
                out.append(str(home.parent if home.name == "bin" else home))
        return out

    def _tool_path_mounts(self, hidden: list[str]) -> list[str]:
        """Read-only binds for PATH entries that the tmpfs masks hid (`~/.local/bin/uv`, nvm).

        Tools installed under /home would otherwise vanish inside the sandbox (#76). Only the
        PATH directories themselves are re-exposed, read-only; never a hidden root, `$HOME`,
        the workspace, or anything under a credential/config directory.
        """
        masked = [*hidden, os.path.expanduser("~")]
        ws = self.workspace_root
        seen: list[str] = []
        venv = self._venv_prefixes()
        for entry in [*os.environ.get("PATH", "").split(os.pathsep), *venv]:
            if not entry or not os.path.isabs(entry) or not os.path.isdir(entry):
                continue
            real = Path(entry).resolve()
            if (
                str(real) in masked
                or real == ws
                or ws in real.parents
                or not any(real.is_relative_to(m) for m in masked)
                or _PRIVATE_DIR_NAMES & set(real.parts)
                or str(real) in seen
            ):
                continue
            seen.append(str(real))
        args = [a for d in seen[:_MAX_PATH_MOUNTS] for a in ("--ro-bind", d, d)]
        for raw in venv:  # uv names the prefix by a symlink (`cpython-3.14-...` -> `3.14.4-...`)
            target = str(Path(raw).resolve())
            if target != raw and target in seen:
                args += ["--symlink", target, raw]
        return args

    def _build_exec_argv(self, cmd: str) -> list[str]:
        """Wrap command in Linux `bwrap` kernel sandbox if available, else standard bash."""
        if self.use_kernel_sandbox and _can_use_bwrap():
            ws = str(self.workspace_root)
            hidden = [d for d in _HIDDEN_HOST_DIRS if os.path.isdir(d)]
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
                *[a for d in hidden for a in ("--tmpfs", d)],
                *self._tool_path_mounts(hidden),
                *_host_socket_masks(),
                "--bind" if self.profile == "workspace-write" else "--ro-bind",
                ws,
                ws,
                *self._protected_mounts(),
                "--chdir",
                ws,
                "--unshare-pid",
                "--unshare-ipc",
                *([] if self.network else ["--unshare-net"]),
                "--die-with-parent",
                "--new-session",
                "--",
                "bash",
                "-c",
                cmd,
            ]
            return bwrap_cmd
        if not self.network:
            raise SandboxViolationError(
                "Sandbox violation: network isolation (`--no-network`) requires `bwrap`, "
                "which is unavailable; refusing to run un-isolated."
            )
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

        combined = _compact_output(combined, self.workspace_root)
        if not combined:
            combined = f"[exit {returncode}: no output]" + (
                " Command succeeded." if returncode == 0 else ""
            )
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
