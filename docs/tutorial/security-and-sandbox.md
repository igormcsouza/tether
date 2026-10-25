# Security and Sandbox

*For: anyone running tether on a real machine. After this page you know exactly what a session can touch and how to narrow it.*

Tether never relies on system prompt instructions ("please do not read `.env` or run `rm -rf`") for safety. Security boundaries around `bash` and `edit` are enforced **deterministically by `SandboxPolicy` and the OS kernel**.

## Sandbox Profiles

| Profile | File Reads (`edit view`) | File Writes (`edit write`/`replace`) | `bash` Execution |
|---|---|---|---|
| `workspace-write` *(default)* | Allowed inside `workspace_root` (except protected paths) | Allowed inside `workspace_root` (except protected paths) | Allowed inside `workspace_root` (with kernel `bwrap` or command guard) |
| `read-only` | Allowed inside `workspace_root` (except protected paths) | Blocked (`SandboxViolationError`) | Restricted to read-only inspection allowlist (`ls`, `cat`, `grep`, `git`, `rg`, etc.) |
| `full-access` | Allowed inside `workspace_root` | Allowed inside `workspace_root` | Allowed without command denylist (still scrubs secrets unless disabled) |

## Four Layers of Deterministic Defense

### 1. Canonical Path Confinement (`resolve_safe_path`)
Every path passed to `edit` or referenced in `bash` is canonicalized via `Path.resolve()` and verified to reside inside `workspace_root`. Traversal attempts (`../../etc/passwd`) raise `SandboxViolationError` before touching the filesystem. For `bash`, the kernel jail (below) is the boundary when `bwrap` is available: path and `.env` text checks on the command line run only in the no-`bwrap` fallback, so harmless commands such as `ls ~/..` are not refused for how they look. The cheap red lines (`sudo`, `su`, disk tools, `rm -rf /`, `chmod 777`, fork bombs, `~/.ssh`) are checked in both modes. `.env.example`, `.env.sample`, `.env.template` and `.env.dist` are not treated as secrets.

### 2. Protected Sensitive Paths
Even within `workspace_root`, Tether deterministically blocks access to sensitive files and directories:

- `.env` and `.env.*`
- `.git/config` and `.git/hooks/*`
- `.tether/*` (the harness's own SQLite database)
- `.ssh/*`, `id_rsa`, `id_ed25519`

### 3. Environment Allowlist
`bash` subprocesses receive only a small allowlist of variables (`PATH`, `LANG`, `LC_*`, `TERM`, `TZ`, `USER`, `LOGNAME`, `SHELL`, `TMPDIR`, `VIRTUAL_ENV`, `CI`, `PYTHONPATH`, ...) plus `HOME`/`PWD` set to the workspace. Everything else (`DATABASE_URL`, `STRIPE_*`, `*_WEBHOOK`, cloud and API keys, session variables) is dropped, so a secret with an unexpected name cannot leak. To pass something through deliberately, set `TETHER_ENV_PASSTHROUGH=NAME1,NAME2`.

### 4. Linux Bubblewrap (`bwrap`) Kernel Isolation
On Linux, when `bwrap` is available and functional, `bash` subprocesses automatically execute inside an unprivileged user/mount/IPC/PID namespace:

- `/` (`usr`, `bin`, `lib`, `etc`) is mounted **read-only** (`--ro-bind`).
- `$HOME` is masked with an empty ephemeral `--tmpfs`.
- `workspace_root` is bind-mounted (`--bind` in `workspace-write` mode, `--ro-bind` in `read-only` mode).
- Secret-looking files inside the workspace at any depth (`.env*`, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, `authorized_keys`), plus `.tether/`, `.git/config` and `.git/hooks`, are masked (`/dev/null` bind or empty `--tmpfs`), so globbing or shell indirection cannot reach them. Files with arbitrary names (for example `creds.json`) cannot be detected; keep them out of the workspace.
- `/home`, `/media`, `/mnt`, `/srv` and `/var/tmp` are hidden behind empty tmpfs, `/run/user` is hidden, and every unix socket under `/run` (for example `docker.sock`) is masked. A read-only bind does not stop `connect()`, so an exposed `docker.sock` would be a host escape. Existing `PATH` directories that sit under a hidden root (`~/.local/bin` for `uv`, nvm's `bin` for `node`) are re-bound read-only so tools installed there still run in `bash` and `--verify` gates; credential directories (`.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`, `.config`) and the hidden roots themselves are never re-exposed.
- `--unshare-pid`, `--unshare-ipc` and `--die-with-parent` ensure runaway child processes are reaped immediately on timeout.

### 5. Optional network isolation (`--no-network`)
By default `bash` keeps network access. `tether run --no-network ...` (or `SandboxPolicy(network=False)`) adds `--unshare-net`, which also separates abstract unix sockets. Sub-agents and pipeline stages inherit it and can never re-enable it. Without `bwrap` the policy cannot be enforced, so `bash` refuses to run (fail closed) instead of running un-isolated. `web fetch` runs in the harness process and is not affected by `--no-network`.

### 6. `web fetch` SSRF guard
`web fetch` resolves the host (and every redirect hop) and refuses non-public addresses: loopback, RFC1918, link-local, and cloud metadata (`169.254.169.254`). Set `TETHER_WEB_ALLOW_PRIVATE=1` to fetch local services on purpose.

## Configuring `SandboxPolicy` in Python

```python
from pathlib import Path
from tether import Harness, SandboxPolicy

policy = SandboxPolicy(
    profile="read-only",
    workspace_root=Path("./my_repo"),
    timeout_seconds=15.0,
    max_output_chars=8000,
    network=False,  # needs bwrap; sub-agents can only keep or narrow it
)

harness = Harness(
    model="ollama/qwen3.5:9b",
    tools=["bash", "edit"],
    sandbox=policy,
)
```

## Example: awk/sed programs that start with `/`

The command guard (the non-`bwrap` fallback check on `bash` commands) treats tokens starting with `/` as absolute paths. Since v0.1.4 the program or pattern argument of `awk`, `sed`, `grep`, `rg` and `perl` (and `/regex{...}` tokens given to them) is not treated as a path, so `awk '/Módulo/ {n++}' plan.md` and `sed -n '/^## M/p' plan.md` work in `bash` and in `verify:` gates. File operands (`sed -n p /etc/hosts`, `awk -f /etc/passwd`) are still checked ([#31](https://github.com/igormcsouza/tether/issues/31)).

## Known limits
- Network is on unless you pass `--no-network`; with it on, `curl` can reach localhost services and the internet.
- There is no process-count limit inside `bwrap` (a fork bomb is only stopped by the timeout).
- Prompt injection still steers the model; the envelope only limits what an injected command can reach.
