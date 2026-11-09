"""Deterministic security sandbox for Tether (workspace jail, env scrubbing, Linux bwrap)."""

from __future__ import annotations

import asyncio
import functools
import glob
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


class SandboxViolationError(PermissionError):
    """Raised when a tool call violates the deterministic SandboxPolicy."""


LIMIT_KEYS = ("cpu", "mem", "procs", "fsize")
# Largest accepted value per key; bigger ones are refused before they reach setrlimit.
LIMIT_MAX = 2**31 - 1


def parse_limits(raw: str | Sequence[str] | Mapping[str, Any] | None) -> dict[str, int]:
    """Normalise resource limits from CLI `K=V` strings or a mapping; empty means no limits."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = [raw]  # one `K=V` item, never iterated char by char
    if isinstance(raw, Mapping):
        pairs: list[tuple[str, Any]] = [(str(k).strip(), v) for k, v in raw.items()]
    else:
        pairs = []
        for item in raw:
            key, sep, value = str(item).partition("=")
            if not sep:
                raise ValueError(f"limit {key.strip() or item!r}: expected K=V, e.g. cpu=60")
            pairs.append((key.strip(), value))
    out: dict[str, int] = {}
    for key, value in pairs:
        if key not in LIMIT_KEYS:
            raise ValueError(f"limit {key}: unknown key; use one of {', '.join(LIMIT_KEYS)}")
        if key in out:
            raise ValueError(f"limit {key}: given more than once")
        if isinstance(value, bool):
            raise ValueError(f"limit {key}: must be a whole number, not a bool")
        if isinstance(value, str):
            try:
                number = int(value.strip())
            except ValueError:
                raise ValueError(f"limit {key}: must be a whole number, got {value!r}") from None
        elif isinstance(value, int):
            number = value
        else:
            raise ValueError(f"limit {key}: must be a whole number, got {value!r}")
        if number <= 0:
            raise ValueError(f"limit {key}: must be positive, got {number}")
        if number > LIMIT_MAX:
            raise ValueError(f"limit {key}: too large, the maximum is {LIMIT_MAX}")
        out[key] = number
    return out


def _limit_setter(limits: Mapping[str, int]) -> Callable[[], None]:
    """Build the preexec_fn that applies rlimits in the forked child before exec."""
    import resource  # stdlib, Linux only; imported lazily so other platforms never load it

    def apply() -> None:
        mib = 1024 * 1024
        if "cpu" in limits:
            _set_rlimit(resource, resource.RLIMIT_CPU, limits["cpu"], limits["cpu"] + 1)
        if "mem" in limits:
            _set_rlimit(resource, resource.RLIMIT_DATA, limits["mem"] * mib)
        if "procs" in limits:
            _set_rlimit(resource, resource.RLIMIT_NPROC, limits["procs"])
        if "fsize" in limits:
            _set_rlimit(resource, resource.RLIMIT_FSIZE, limits["fsize"] * mib)

    return apply


def _set_rlimit(resource: Any, which: int, soft: int, hard: int | None = None) -> None:
    # Clamp to the current hard limit: raising a hard limit fails and surfaces as an opaque error.
    _, current_hard = resource.getrlimit(which)
    want_hard = soft if hard is None else hard
    if current_hard != resource.RLIM_INFINITY:
        want_hard = min(want_hard, current_hard)
        soft = min(soft, want_hard)
    resource.setrlimit(which, (soft, want_hard))


def _children_cpu_seconds() -> float:
    """User+system CPU seconds of all reaped children of this process (Linux only)."""
    import resource

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return float(usage.ru_utime + usage.ru_stime)


def parse_web_allow(raw: str | Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalise a `web_allow` domain list; None means unset, () means deny every host."""
    if raw is None:
        return None
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    cleaned: list[str] = []
    for item in items:
        entry = str(item).strip().lower().rstrip(".")
        if not entry:
            raise ValueError("web_allow has an empty entry; give domains such as python.org")
        if "://" in entry or any(ch in entry for ch in "/@:") or entry == "*":
            raise ValueError(
                f"web_allow entry {item!r} must be a bare domain like python.org or *.python.org"
            )
        stars = entry.count("*")
        if any(ch.isspace() for ch in entry) or (
            stars and (not entry.startswith("*.") or stars > 1)
        ):
            raise ValueError(
                f"web_allow entry {item!r} may only contain a leading '*.' wildcard, with no spaces"
            )
        cleaned.append(entry)
    return tuple(cleaned)


def _entry_within(child: str, parent: str) -> bool:
    """True when every host the child entry matches is also matched by the parent entry."""
    base = child.removeprefix("*.")
    if parent.startswith("*."):
        return base.endswith("." + parent[2:])
    return base == parent or base.endswith("." + parent)


def _narrow_web_allow(
    parent: tuple[str, ...] | None, child: Sequence[str] | str | None
) -> tuple[str, ...] | None:
    """A child may only keep entries the parent already allows; an unset child inherits."""
    if child is None:
        return parent
    requested = parse_web_allow(child) or ()
    if parent is None:
        return requested
    return tuple(c for c in requested if any(_entry_within(c, p) for p in parent))


_OUTSIDE_META_RE = re.compile(r"[;&|`<>\n]|\$\(")
_GIT_UNSAFE_OPTS = frozenset(
    {
        "-c",
        "-C",
        "--exec",
        "--exec-path",
        "--receive-pack",
        "--upload-pack",
        "--git-dir",
        "--work-tree",
        "--config-env",
        "--namespace",
    }
)


def _git_unsafe_option(cmd: str) -> bool:
    """True when a `git` command carries an option that runs code or leaves the repo.

    Such a command stays in the jail even when its prefix is allowlisted (#59 security).
    Attached forms (`-C/etc`, `-ccore.x=y`) and `--opt=value` forms are caught too.
    """
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return False
    if not argv or argv[0] != "git":
        return False
    for tok in argv[1:]:
        if tok.startswith(("-c", "-C")):
            return True
        if tok.split("=", 1)[0] in _GIT_UNSAFE_OPTS:
            return True
    return False


_GIT_JAILED_REMOTE_OPS = frozenset({"add", "set-url", "set-head"})
_GIT_JAILED_SECTIONS = frozenset({"alias", "url", "include", "includeif", "credential"})
_GIT_JAILED_KEYS = frozenset(
    {
        "core.sshcommand",
        "core.hookspath",
        "core.fsmonitor",
        "core.pager",
        "core.editor",
        "gpg.program",
        "http.proxy",
    }
)


def _git_config_key_jailed(token: str) -> bool:
    # Keys that run code or redirect the repo when written to .git/config (case-insensitive).
    key = token.lower()
    if key.split(".", 1)[0] in _GIT_JAILED_SECTIONS or key in _GIT_JAILED_KEYS:
        return True
    return key.startswith("http.") and key.endswith(".proxy")


def _git_jailed(head: list[str], want: list[str]) -> bool:
    # True when a git command stays in the jail although an allow entry matches its prefix.
    # A bare `git` entry never covers `git config`, `git remote add|set-url|set-head` or
    # `git submodule`; the entry must name that subcommand itself. `git config` with a risky
    # key stays jailed even then.
    if not head or head[0] != "git":
        return False
    args = head[1:]
    idx = next((i for i, tok in enumerate(args) if not tok.startswith("-")), None)
    if idx is None:
        return False
    named = len(want) - 1  # tokens the entry names after `git`
    sub = args[idx]
    if sub == "config":
        if any(_git_config_key_jailed(t) for t in args[idx + 1 :] if not t.startswith("-")):
            return True
        return named <= idx
    if sub == "submodule":
        return named <= idx
    if sub == "remote":
        pos = next((i for i in range(idx + 1, len(args)) if not args[i].startswith("-")), None)
        if pos is not None and args[pos] in _GIT_JAILED_REMOTE_OPS:
            return named <= pos
    return False


_ALLOW_FILE_HINT = 'expected {"allow": ["git push", ...]}; fix or delete the file'


def parse_allow_outside(raw: Sequence[str] | None) -> tuple[str, ...]:
    """Normalise `allow_outside` prefixes: single-spaced tokens, no duplicates, order kept."""
    if raw is None:
        return ()
    cleaned: list[str] = []
    for item in raw:
        entry = " ".join(str(item).split())
        if not entry:
            raise ValueError("allow_outside has an empty entry; give a command such as `git push`")
        if _OUTSIDE_META_RE.search(entry):
            raise ValueError(
                f"allow_outside entry {_clip(item)!r} has a shell metacharacter; "
                "give a plain command prefix"
            )
        if entry not in cleaned:
            cleaned.append(entry)
    return tuple(cleaned)


def load_allow_file(root: Path) -> tuple[str, ...]:
    """Entries of `<root>/.tether/allow.json`; a missing file allows nothing."""
    path = root / ".tether" / "allow.json"
    if not path.is_file():
        return ()

    def bad(problem: str) -> ValueError:
        return ValueError(f".tether/allow.json: {problem}; {_ALLOW_FILE_HINT}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise bad(f"not valid JSON ({exc.msg})") from exc
    entries = data.get("allow") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        raise bad('the "allow" key must be a list of strings')
    try:
        return parse_allow_outside(entries)
    except ValueError as exc:
        raise bad(str(exc)) from exc


def _narrow_allow_outside(parent: tuple[str, ...], child: Sequence[str] | None) -> tuple[str, ...]:
    """A child keeps only the parent's entries it also requests; it can never add one."""
    if child is None:
        return parent
    requested = set(parse_allow_outside(child))
    return tuple(entry for entry in parent if entry in requested)


class SandboxUnavailableError(RuntimeError):
    """A write session needs bwrap and the caller did not opt out."""


UNSANDBOXED_NOTICE = "[sandbox] bwrap not available, running with command checks only"
# Printed once per process, at session creation, so repeated runs do not flood stderr.
_UNSANDBOXED_NOTICE_SHOWN: bool = False


def _clip(value: object, limit: int = 60) -> str:
    # Interpolated paths and tokens are capped so no refusal message grows with its input.
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _protected_hint(rel: str) -> str:
    # The safe alternative depends on the kind of protected path that was hit.
    parts = rel.split("/")
    if any(part.startswith(".env") for part in parts):
        return "use `.env.example`"
    if rel.startswith(".git/"):
        return "change git config outside the session"
    if ".tether" in parts:
        return "keep files outside `.tether/`"
    return "keep keys outside the workspace"


def _refusal(rule: str, instead: str, flag: str | None = None) -> SandboxViolationError:
    # One format for every refusal: the rule, a safe alternative, and the flag that would permit
    # it when one exists. Built only on refusal, so it costs no static prompt tokens.
    msg = f"Sandbox violation: {rule}. Instead: {instead}."
    if flag:
        msg += f" Flag: {flag}."
    return SandboxViolationError(msg)


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

_BLOCKED_BASH_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"(?:^|[;&|()\s])sudo\b"),
        "`sudo` privilege escalation is blocked",
        "run the command without elevated privileges",
    ),
    (
        re.compile(r"(?:^|[;&|()\s])su\b"),
        "`su` user switching is blocked",
        "run the command as the current user",
    ),
    (
        re.compile(r"(?:^|[;&|()\s])(?:mkfs|fdisk|parted|mount|umount)\b"),
        "disk utilities are blocked",
        "use `cp` or `ls` on workspace files; disk changes need the user",
    ),
    (
        re.compile(r"(?:^|[;&|()\s])dd\s+if="),
        "`dd` raw block operations are blocked",
        "use `cp` or `head -c` on workspace files",
    ),
    (
        re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+/(?:\s|$|\*)"),
        "`rm -rf /` is blocked",
        "target a path inside the workspace, e.g. `./build`",
    ),
    (
        re.compile(r"chmod\s+(?:-R\s+)?777\b"),
        "`chmod 777` is blocked",
        "use `chmod 755` for scripts or `chmod 644` for files",
    ),
    (
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"),
        "fork bombs are blocked",
        "use a non-destructive command",
    ),
    (
        re.compile(r"(?:~|\$HOME)/\.ssh\b|/etc/(?:shadow|sudoers)\b"),
        "access to system secrets is blocked",
        "use workspace paths instead of `~/.ssh` or `/etc`",
    ),
]

# Text rules that bwrap's mounts already enforce (masked secrets, hidden `.tether/`, read-only root,
# hidden home). They only guard the no-bwrap fallback: with the kernel jail they would just refuse
# harmless commands such as `cat .env.example` (#125).
_MOUNT_ENFORCED_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"(?:^|[\s/\"'])(\.env(?!\.(?:example|sample|template|dist)\b)"
            r"(?:\.[a-zA-Z0-9_-]+)?)\b"
        ),
        "access to protected path `.env` is denied",
        "use `.env.example`",
    ),
    (
        re.compile(r"(?:^|[\s/\"':=])\.tether(?:/|\b)"),
        "access to protected path `.tether` is denied",
        "keep files outside `.tether/`",
    ),
    (
        re.compile(r"(?:^|[\s/\"'])\.git/(?:config|hooks)\b"),
        "access to protected path `.git/config` is denied",
        "change git config outside the session",
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


_ISOLATION_MSG = (
    "Sandbox unavailable: workspace-write needs bwrap (Linux kernel sandbox), which is not "
    "available here. Install bubblewrap (e.g. apt install bubblewrap, then tether doctor), run "
    "inside a container with TETHER_SANDBOX=container, or pass --allow-unsandboxed (SDK/MCP: "
    "allow_unsandboxed=True) to run with command checks only."
)


def _container_mode() -> bool:
    """`TETHER_SANDBOX=container`: the container is the sandbox. Other values fail loudly."""
    value = os.environ.get("TETHER_SANDBOX", "").strip()
    if value and value != "container":
        raise SandboxUnavailableError(
            f"TETHER_SANDBOX={_clip(value)!r} is not supported; use TETHER_SANDBOX=container "
            "or unset it."
        )
    return value == "container"


_RULE_LINE = re.compile(r"^(?:={20,}|-{20,})$\n?", re.M)


_CARET = re.compile(r"^\s*[\^~]+\s*$")


def _collapse_tracebacks(lines: list[str]) -> list[str]:
    """Keep the last two frames of each Python traceback (call site + cause), drop `^^^` rows."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        i += 1
        if out[-1] != "Traceback (most recent call last):":
            continue
        frames: list[list[str]] = []
        while i < len(lines) and lines[i].startswith("  File "):
            frames.append([lines[i]])
            i += 1
            while i < len(lines) and lines[i].startswith("    "):
                if not _CARET.match(lines[i]):
                    frames[-1].append(lines[i])
                i += 1
        if len(frames) > 2:
            out.append(f"  ... {len(frames) - 2} frames ...")
            frames = frames[-2:]
        out.extend(line for frame in frames for line in frame)
    return out


def _compact_output(text: str, root: Path) -> str:
    """Token saver: drop rule lines, the workspace prefix and the middle of long tracebacks."""
    text = _RULE_LINE.sub("", text.replace(f"{root}/", ""))
    return "\n".join(_collapse_tracebacks(text.split("\n")))


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
    # None = unset (today's behaviour); () = deny every host. Set by --web-allow / web_allow.
    web_allow: tuple[str, ...] | None = None
    # Opt-out for write profiles when bwrap is missing (SDK / CLI / MCP). Only ever narrowed.
    allow_unsandboxed: bool = False
    # Command prefixes that run outside bwrap (`--allow`); a child can only narrow this.
    allow_outside: tuple[str, ...] = ()
    # Optional rlimits (LIMIT_KEYS). Empty = off, the default.
    limits: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()
        if self.profile not in ("workspace-write", "read-only"):
            raise ValueError(f"Unsupported sandbox profile: {self.profile}")
        self.web_allow = parse_web_allow(self.web_allow)
        self.allow_outside = parse_allow_outside(self.allow_outside)
        self.limits = parse_limits(self.limits)
        if self.limits and sys.platform != "linux":
            key = next(iter(self.limits))
            raise ValueError(
                f"limit {key}: needs Linux (RLIMIT_DATA/RLIMIT_NPROC); remove --limit {key}"
            )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "profile": self.profile,
            "workspace_root": str(self.workspace_root),
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
            "use_kernel_sandbox": self.use_kernel_sandbox,
            "network": self.network,
            "verify_commands": list(self.verify_commands),
            "web_allow": None if self.web_allow is None else list(self.web_allow),
            "allow_unsandboxed": self.allow_unsandboxed,
            "allow_outside": list(self.allow_outside),
        }
        if self.limits:
            data["limits"] = dict(self.limits)
        return data

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
            web_allow=parse_web_allow(data.get("web_allow")),
            allow_unsandboxed=bool(data.get("allow_unsandboxed", False)),
            allow_outside=parse_allow_outside(data.get("allow_outside")),
            limits=parse_limits(data.get("limits")),
        )

    def with_allow_file(self) -> SandboxPolicy:
        """A copy whose allow_outside also holds the project's `.tether/allow.json` entries."""
        merged = parse_allow_outside([*load_allow_file(self.workspace_root), *self.allow_outside])
        return replace(self, allow_outside=merged)

    def attenuate(
        self,
        child_profile: str | None = None,
        child_network: bool | None = None,
        child_web_allow: Sequence[str] | str | None = None,
        child_allow_unsandboxed: bool | None = None,
        child_allow_outside: Sequence[str] | None = None,
        child_limits: Mapping[str, int] | None = None,
    ) -> SandboxPolicy:
        """Create a child SandboxPolicy that can only narrow (never escalate) privileges."""
        limits = dict(self.limits)
        for key, value in parse_limits(child_limits).items():
            if key in limits and value > limits[key]:
                raise ValueError(f"limit {key}: child cannot raise {limits[key]} to {value}")
            limits[key] = value
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
            web_allow=_narrow_web_allow(self.web_allow, child_web_allow),
            allow_unsandboxed=self.allow_unsandboxed and child_allow_unsandboxed is not False,
            allow_outside=_narrow_allow_outside(self.allow_outside, child_allow_outside),
            limits=limits,
        )

    def _limit_hit(self, rc: int, output: str, cpu_used: float | None = None) -> str | None:
        """Name the first configured limit that explains a failed command, else None.

        `cpu_used` is the child's CPU seconds; a SIGKILL counts as a cpu hit only when that
        time reached the limit (RLIMIT_CPU's hard kill), so `kill -9` or the OOM killer do not.
        """
        if not self.limits:
            return None
        checks: list[tuple[str, bool, str, str]] = []
        if "cpu" in self.limits:
            killed = rc in {-signal.SIGKILL, 128 + signal.SIGKILL}
            cpu_reached = cpu_used is not None and cpu_used >= self.limits["cpu"] - 0.05
            checks.append(
                (
                    "cpu",
                    rc in {-signal.SIGXCPU, 128 + signal.SIGXCPU} or (killed and cpu_reached),
                    f"cpu {self.limits['cpu']}s",
                    "do less work per command (smaller input, fewer iterations) or split it into "
                    "steps.",
                )
            )
        if "fsize" in self.limits:
            checks.append(
                (
                    "fsize",
                    rc in {-signal.SIGXFSZ, 128 + signal.SIGXFSZ}
                    or (rc != 0 and "File too large" in output),
                    f"fsize {self.limits['fsize']} MB",
                    "write less data or split the output into smaller files.",
                )
            )
        if "procs" in self.limits:
            checks.append(
                (
                    "procs",
                    rc != 0
                    and ("Resource temporarily unavailable" in output or "fork: retry" in output),
                    f"procs {self.limits['procs']}",
                    "start fewer processes at once (no background loops, lower -j).",
                )
            )
        if "mem" in self.limits:
            markers = ("MemoryError", "Cannot allocate memory", "bad_alloc", "out of memory")
            checks.append(
                (
                    "mem",
                    rc != 0 and any(m in output for m in markers),
                    f"mem {self.limits['mem']} MB",
                    "process the data in smaller chunks or stream it.",
                )
            )
        for _key, hit, label, hint in checks:
            if hit:
                return f"[limit hit: {label}] Instead: {hint}"
        return None

    def _relies_on_bwrap(self) -> bool:
        # A write session that asked for the kernel sandbox, on a host without one.
        return (
            self.profile != "read-only"
            and self.use_kernel_sandbox
            and not _can_use_bwrap()
            and not _container_mode()
        )

    def isolation_error(self) -> str | None:
        """The refusal message when this policy needs bwrap and has no opt-out, else None."""
        _container_mode()  # validate TETHER_SANDBOX on every host, before any short-circuit
        if self.allow_unsandboxed or not self._relies_on_bwrap():
            return None
        return _ISOLATION_MSG

    def require_isolation(self) -> None:
        """Refuse before any model call; with the opt-out, print the notice once per process."""
        global _UNSANDBOXED_NOTICE_SHOWN
        err = self.isolation_error()
        if err is not None:
            raise SandboxUnavailableError(err)
        if not _UNSANDBOXED_NOTICE_SHOWN and self._relies_on_bwrap():
            print(UNSANDBOXED_NOTICE, file=sys.stderr, flush=True)
            _UNSANDBOXED_NOTICE_SHOWN = True

    def mode(self) -> str:
        """What `tether status` shows for the session."""
        return "bwrap" if self.use_kernel_sandbox and _can_use_bwrap() else "command checks only"

    def resolve_safe_path(self, raw_path: str | Path, *, write: bool = False) -> Path:
        """Resolve a path and enforce workspace confinement + sensitive-file protection."""
        if write and self.profile == "read-only":
            raise _refusal(
                "file writes are disabled in `read-only` profile",
                "read the file, or use a write-capable profile",
                "--sandbox workspace-write",
            )

        p = Path(raw_path)
        candidate = (self.workspace_root / p).resolve() if not p.is_absolute() else p.resolve()

        if not candidate.is_relative_to(self.workspace_root):
            raise _refusal(
                f"path `{_clip(raw_path)}` resolves outside workspace",
                "use a relative path inside the workspace",
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
            access = "not writable" if write else "not accessible"
            raise _refusal(
                f"access to protected path `{_clip(rel_str)}` is denied; "
                f"it is protected and {access}",
                _protected_hint(rel_str),
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

    def validate_bash_command(self, cmd: str, *, text_rules: bool = False) -> None:
        """Deterministically validate a shell command against sandbox rules."""
        stripped = cmd.strip()
        if not stripped:
            raise _refusal("Empty command", "pass a non-empty `cmd`")

        # text_rules forces the fallback checks, e.g. for commands that run outside the jail.
        kernel = self.use_kernel_sandbox and _can_use_bwrap() and not text_rules
        for pattern, reason, instead in (
            _BLOCKED_BASH_PATTERNS if kernel else _BLOCKED_BASH_PATTERNS + _MOUNT_ENFORCED_PATTERNS
        ):
            if pattern.search(stripped):
                raise _refusal(reason, instead)

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
                raise _refusal(
                    "parent directory traversal (`..`) is blocked",
                    "use a path inside the workspace, e.g. `./src`",
                )
            if tok.startswith("/") and not tok.startswith(("/dev/null", "/dev/zero", "/tmp")):
                resolved = Path(tok).resolve()
                if not resolved.is_relative_to(self.workspace_root):
                    raise _refusal(
                        f"absolute path `{_clip(tok)}` is outside workspace",
                        "use a relative path inside the workspace",
                    )

        if self.profile == "read-only":
            if any(
                op in stripped
                for op in (">", ">>", "| tee", "rm ", "mv ", "cp ", "mkdir ", "touch ")
            ):
                raise _refusal(
                    "mutating shell commands are blocked in `read-only` profile",
                    "use an inspect-only command such as `cat`, `ls` or `grep`",
                    "--sandbox workspace-write",
                )
            first_bin = Path(tokens[0]).name if tokens else ""
            if first_bin not in _READONLY_ALLOWED_BINARIES:
                raise _refusal(
                    f"binary `{first_bin}` is not in the `read-only` allowlist",
                    "use an allowlisted binary such as `ls`, `cat`, `grep` or `rg`",
                    "--sandbox workspace-write",
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
            raise _refusal(
                "network isolation (`--no-network`) requires `bwrap`, which is unavailable; "
                "refusing to run un-isolated",
                "install `bwrap`, or drop `--no-network`",
            )
        return ["bash", "-c", cmd]

    async def execute_bash_with_code(self, cmd: str, stdin: str | None = None) -> tuple[int, str]:
        """Execute a shell command in the deterministic sandbox and return (returncode, output)."""
        effective_cmd = cmd.strip()
        if not effective_cmd and stdin:
            effective_cmd = stdin.strip()
            stdin = None

        entry = self._outside_match(effective_cmd)
        if entry is not None and not _git_unsafe_option(effective_cmd):
            return await self._execute_outside(effective_cmd, entry, stdin)
        self.validate_bash_command(effective_cmd)
        argv = self._build_exec_argv(effective_cmd)
        return await self._run_argv(argv, stdin, env=self.scrub_env(), cwd=str(self.workspace_root))

    def _outside_match(self, cmd: str) -> str | None:
        """The `allow_outside` entry whose whole tokens start the command, else None.

        Text after the first shell metacharacter still counts, so `git push;rm x` is refused
        rather than silently jailed.
        """
        if self.profile == "read-only" or not self.allow_outside:
            return None  # read-only never mutates, and `git push` mutates
        head = _OUTSIDE_META_RE.split(cmd, maxsplit=1)[0].split()
        for entry in self.allow_outside:
            want = entry.split()
            if head[: len(want)] == want and not _git_jailed(head, want):
                return entry
        return None

    async def _execute_outside(self, cmd: str, entry: str, stdin: str | None) -> tuple[int, str]:
        """Run an allowlisted command with no shell, no bwrap, and the scrubbed environment."""
        if _OUTSIDE_META_RE.search(cmd):
            raise _refusal(
                f"`{_clip(entry)}` runs outside the jail, so shell metacharacters "
                "(`;`, `&&`, `||`, `|`, `$(`, backtick, `>`, `<`, newline) are refused",
                "run the allowed command alone, one per call",
            )
        if not self.network:
            raise _refusal(
                f"`{_clip(entry)}` runs outside the jail, which `--no-network` forbids",
                "drop `--no-network` or the --allow entry",
            )
        try:
            argv = shlex.split(cmd)
        except ValueError as exc:
            raise _refusal(
                f"unbalanced quotes in `{_clip(cmd)}`", "close every quote, one command per call"
            ) from exc
        self.validate_bash_command(cmd, text_rules=True)
        env = self.scrub_env()
        env["HOME"] = os.path.expanduser("~")  # git and gh read ~/.gitconfig and credentials
        return await self._run_argv(argv, stdin, env=env, cwd=str(self.workspace_root))

    async def _run_argv(
        self, argv: list[str], stdin: str | None, *, env: dict[str, str], cwd: str
    ) -> tuple[int, str]:
        """Run argv under the shared wall-clock cap and output compaction (both paths use it)."""
        extra: dict[str, Any] = {}
        if self.limits:
            # preexec_fn is unsafe with threads; tether spawns from the asyncio loop only.
            extra["preexec_fn"] = _limit_setter(self.limits)
        cpu_before = _children_cpu_seconds() if "cpu" in self.limits else None
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
            **extra,
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
        cpu_used = None if cpu_before is None else _children_cpu_seconds() - cpu_before
        hit = self._limit_hit(returncode, combined, cpu_used)
        if hit:
            combined = f"{combined}\n{hit}"
        return returncode, combined

    async def execute_bash(self, cmd: str, stdin: str | None = None) -> str:
        """Execute a shell command inside the deterministic sandbox."""
        _, combined = await self.execute_bash_with_code(cmd, stdin=stdin)
        return combined
