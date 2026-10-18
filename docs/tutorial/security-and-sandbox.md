# Security and Sandbox

Tether never relies on system prompt instructions ("please do not read `.env` or run `rm -rf`") for safety. Security boundaries around `bash` and `edit` are enforced **deterministically by `SandboxPolicy` and the OS kernel**.

## Sandbox Profiles

| Profile | File Reads (`edit view`) | File Writes (`edit write`/`replace`) | `bash` Execution |
|---|---|---|---|
| `workspace-write` *(default)* | Allowed inside `workspace_root` (except protected paths) | Allowed inside `workspace_root` (except protected paths) | Allowed inside `workspace_root` (with kernel `bwrap` or command guard) |
| `read-only` | Allowed inside `workspace_root` (except protected paths) | Blocked (`SandboxViolationError`) | Restricted to read-only inspection allowlist (`ls`, `cat`, `grep`, `git`, `rg`, etc.) |
| `full-access` | Allowed inside `workspace_root` | Allowed inside `workspace_root` | Allowed without command denylist (still scrubs secrets unless disabled) |

## Four Layers of Deterministic Defense

### 1. Canonical Path Confinement (`resolve_safe_path`)
Every path passed to `edit` or referenced in `bash` is canonicalized via `Path.resolve()` and verified to reside inside `workspace_root`. Traversal attempts (`../../etc/passwd`) raise `SandboxViolationError` before touching the filesystem.

### 2. Protected Sensitive Paths
Even within `workspace_root`, Tether deterministically blocks access to sensitive files and directories:

- `.env` and `.env.*`
- `.git/config` and `.git/hooks/*`
- `.tether/*` (the harness's own SQLite database)
- `.ssh/*`, `id_rsa`, `id_ed25519`

### 3. Secret Environment Scrubbing
Before spawning any `bash` subprocess, Tether strips sensitive credentials from `os.environ`:

- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`
- `TAVILY_API_KEY`, `BRAVE_API_KEY`, `GITHUB_TOKEN`, `GH_TOKEN`
- Any variable matching `AWS_*`, `*_SECRET*`, `*_TOKEN*`, `*_PASSWORD*`, or `*_PRIVATE_KEY*`

### 4. Linux Bubblewrap (`bwrap`) Kernel Isolation
On Linux, when `bwrap` is available and functional, `bash` subprocesses automatically execute inside an unprivileged user/mount/IPC/PID namespace:

- `/` (`usr`, `bin`, `lib`, `etc`) is mounted **read-only** (`--ro-bind`).
- `$HOME` is masked with an empty ephemeral `--tmpfs`.
- `workspace_root` is bind-mounted (`--bind` in `workspace-write` mode, `--ro-bind` in `read-only` mode).
- `.env*`, `.tether/`, `.git/config` and `.git/hooks` inside the workspace are masked (`/dev/null` bind or empty `--tmpfs`), so globbing or shell indirection cannot reach them; `/run/user` is hidden to block the ssh/gpg agent sockets.
- `--unshare-pid`, `--unshare-ipc` and `--die-with-parent` ensure runaway child processes are reaped immediately on timeout.

## Configuring `SandboxPolicy` in Python

```python
from pathlib import Path
from tether import Harness, SandboxPolicy

policy = SandboxPolicy(
    profile="read-only",
    workspace_root=Path("./my_repo"),
    timeout_seconds=15.0,
    max_output_chars=8000,
)

harness = Harness(
    model="ollama/qwen3.5:9b",
    tools=["bash", "edit"],
    sandbox=policy,
)
```
