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
- Secret-looking files inside the workspace at any depth (`.env*`, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, `authorized_keys`), plus `.tether/`, `.git/config` and `.git/hooks`, are bound over with an empty read-only file, so they read as empty (git and recursive tools keep working) and cannot be written or deleted. Globbing or shell indirection cannot reach their contents. Files with arbitrary names (for example `creds.json`) cannot be detected; keep them out of the workspace.
- `/home`, `/media`, `/mnt`, `/srv` and `/var/tmp` are hidden behind empty tmpfs, `/run/user` is hidden, and every unix socket under `/run` (for example `docker.sock`) is masked. A read-only bind does not stop `connect()`, so an exposed `docker.sock` would be a host escape. Existing `PATH` directories that sit under a hidden root (`~/.local/bin` for `uv`, nvm's `bin` for `node`) are re-bound read-only so tools installed there still run in `bash` and `--verify` gates; credential directories (`.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`, `.config`) and the hidden roots themselves are never re-exposed.
- `--unshare-pid`, `--unshare-ipc` and `--die-with-parent` ensure runaway child processes are reaped immediately on timeout.

### Without bwrap (fail closed)
Without `bwrap` (macOS, Windows, or Linux without bubblewrap) only the command-text checks remain, and those are easy to get around (`python -c ...`). So a `workspace-write` session with the kernel sandbox on is refused before the first model call (exit `1`). The message names the three ways out:

- Install bubblewrap (`apt install bubblewrap`, then `tether doctor`).
- Pass `--allow-unsandboxed` (`tether run`, `tether pipeline`), `SandboxPolicy(allow_unsandboxed=True)` or `Harness(allow_unsandboxed=True)` in Python, or the MCP `tether_run` argument `allow_unsandboxed`. The session then runs and prints one `[sandbox] bwrap not available, running with command checks only` line on stderr per process.
- In Docker, set `TETHER_SANDBOX=container`: the container is the sandbox. No refusal and no notice. Any other value of `TETHER_SANDBOX` is refused. The command-text checks still apply in this mode.

`read-only` sessions and `SandboxPolicy(use_kernel_sandbox=False)` are not refused. Sub-agents and pipeline stages inherit the opt-out and can only drop it. `tether status <id>` shows `sandbox: bwrap` or `sandbox: command checks only`.

### 5. Optional network isolation (`--no-network`)
By default `bash` keeps network access. `tether run --no-network ...` (or `SandboxPolicy(network=False)`) adds `--unshare-net`, which also separates abstract unix sockets. Sub-agents and pipeline stages inherit it and can never re-enable it. Without `bwrap` the policy cannot be enforced, so `bash` refuses to run (fail closed) instead of running un-isolated. `web fetch` runs in the harness process and is not affected by `--no-network`.

### 6. `web fetch` SSRF guard
`web fetch` resolves the host (and every redirect hop) and refuses non-public addresses: loopback, RFC1918, link-local, and cloud metadata (`169.254.169.254`). Set `TETHER_WEB_ALLOW_PRIVATE=1` to fetch local services on purpose.

### 7. Web domain allowlist (`--web-allow`)
By default the `web` tool can reach any public host. `tether run --web-allow python.org,*.github.com` (or `SandboxPolicy(web_allow=...)`) limits it to the listed domains.

- A bare `d` such as `python.org` matches `python.org` and every subdomain of it (`docs.python.org`). `*.d` such as `*.python.org` matches subdomains of `d` only, not `d` itself.
- IP literals (such as `http://93.184.216.34/`) are always refused, even if they look public.
- Redirects are checked hop by hop. A redirect to a host outside the list is refused.
- Search results are filtered to the list before the count limit is applied; hidden results are reported as a count.
- Children can only narrow the list. Sub-agents and pipeline stages inherit it and can never widen it.

### 8. Resource limits (`--limit`)
Off by default. `tether run --limit cpu=60 --limit mem=2048` (also `tether pipeline --limit`, `SandboxPolicy(limits={"cpu": 60})` and the MCP `tether_run` argument `limits`) sets rlimits on every `bash` command. Linux only: elsewhere a session with limits is refused with a usage error.

| Key | Unit | Kernel limit | When it is hit |
|-----|------|--------------|----------------|
| `cpu` | seconds of CPU time | `RLIMIT_CPU` | the command gets SIGXCPU (SIGKILL one second later) |
| `mem` | MB | `RLIMIT_DATA` | allocations fail (`MemoryError`, `Cannot allocate memory`) |
| `procs` | processes | `RLIMIT_NPROC` | `fork` fails (`Resource temporarily unavailable`) |
| `fsize` | MB per file | `RLIMIT_FSIZE` | writes past the size fail (`File too large`) |

- When a failed command is explained by a limit, the last output line is `[limit hit: <key> <value>] Instead: <hint>`. A `kill -9` or OOM-killer SIGKILL is only reported as a cpu hit when the command really used its CPU time.
- `mem` uses `RLIMIT_DATA` (heap and anonymous mappings), not `RLIMIT_AS` (all address space) and not a cgroup. Runtimes that reserve large virtual ranges up front still start, but the cap is not a total RSS cap.
- Node and the JVM size their heaps on their own; with a low `mem` they can fail at startup or abort with a heap error. Raise `mem` or set `--max-old-space-size` / `-Xmx` below it.
- `procs` (`RLIMIT_NPROC`) counts every process of your user id on the host, not only the command's own children, so set it with room above what you already run. Root ignores it.
- Limits also apply to `--verify` gate commands, which run through the same sandbox.
- Values are positive whole numbers up to 2147483647. Integral floats such as `1.0` (common from JSON clients) are rejected as "not a whole number"; send `1`.
- Sub-agents and pipeline stages inherit the limits and can only lower them.

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

## Install with the network, work without it

Some tasks need packages from the internet before the model starts, but the model's own commands should not reach the network. Install with `--setup` while the network is on, then run the model with `--no-network`:

```bash
tether run --worktree --setup "uv sync" --no-network --verify "uv run pytest -q" "<goal>"
```

| Flag | What it does |
|---|---|
| `--worktree` | Runs the session in a git worktree on branch `tether/<id>`, so your checkout is not touched until you merge. |
| `--setup "uv sync"` | Runs on the host, with the network on, before the model starts. It is trusted code and is not sandboxed. |
| `--no-network` | Adds `--unshare-net` to the model's `bash`. It requires `bwrap`; without `bwrap` the run fails closed instead of running without isolation. |
| `--verify "uv run pytest -q"` | A gate that must pass before the session can report `done`. |

Output is not shown.

Limits:

- `--setup` is the only step that needs the network to install dependencies. A task where the model must download something while it works keeps the default (network on) and cannot use `--no-network`.
- The `--verify` commands must work without the network once `--setup` has finished. They run inside the same bwrap sandbox as the model's `bash`, so with `--no-network` they have no network either.
- `--no-network` covers the model's `bash` only. `web fetch` runs in the harness process and is not affected by it. To limit which domains `web fetch` may reach, use the web domain allowlist (`--web-allow`, section 7 above).

## When a command is refused

A refusal names the rule, what to do instead, and the flag that would permit it when one exists. Two real messages:

```text
Sandbox violation: `sudo` privilege escalation is blocked. Instead: run the command without elevated privileges.
Sandbox violation: binary `python3` is not in the `read-only` allowlist. Instead: use an allowlisted binary such as `ls`, `cat`, `grep` or `rg`. Flag: --sandbox workspace-write.
```

## 8. Running a command outside the jail

Some commands must reach things the jail hides, such as pushing a branch or opening a pull request. You can allow a prefix to run outside the jail with `--allow` (CLI), `allow` in `.tether/allow.json`, or the `allow` argument of MCP `tether_run`.

- **Whole-token prefix matching.** `--allow "gh pr create"` matches `gh pr create --draft` but not `gh pr createx`. `--allow git` matches any `git` command.
- **No shell.** An allowed command runs as a plain argv with no shell. Shell metacharacters (`;`, `&&`, `||`, `|`, `$(`, backtick, `>`, `<`, newline, and a single background `&`) are refused, so nothing can be chained after the allowed prefix.
- **Never in read-only or `--no-network` sessions.** Read-only sessions never run an allowed command outside. `--no-network` refuses it, because the outside run has no network isolation.
- **`.tether/allow.json` is protected.** The model cannot edit it with `edit` or redirect into it. A missing file means no allowed prefixes. A malformed file fails the run before the first model call.
- **Children can only narrow.** A pipeline stage or an `agent spawn` child keeps the parent's list, or a subset of it. It can never add a prefix.
- **Git options that run code or leave the repo stay jailed.** With `git` allowed, `-c`, `-C`, `--exec`, `--exec-path`, `--receive-pack`, `--upload-pack`, `--git-dir`, `--work-tree`, `--config-env` and `--namespace` (including attached and `=value` forms) fall back to the jailed path.

**Deliberate hole: a whole tool exposes its credentials.** The outside run uses your real `HOME`, so the tool sees `~/.gitconfig`, credential helpers and hooks. Allowing `gh` lets the model run `gh auth token`, which prints your token into the transcript. Prefer narrow prefixes such as `gh pr create` or `git push origin`, and never allow a whole tool you would not run yourself.

## Let a session push a branch

You do not have to list every prefix up front. When the model runs a command whose prefix is in the policy's `escalate` list and not yet allowed, the session pauses as `WAITING_INPUT` (exit 2) and asks its caller once (#59):

```text
$ tether run --tools bash "push the fix"
session ses_127f99a5
[APPROVAL NEEDED] git push origin main
Approving adds `git push` to .tether/allow.json and runs the command outside the jail. Caller: `tether send ses_127f99a5 approve` or `deny`.
$ echo $?
2
$ tether send ses_127f99a5 approve
```

The output of the approved run reaches the model as a follow-up turn. This one is from a real run in a directory that is not a git repository, so the push itself failed:

```text
[Follow-up instruction]: approved; `git push` added to .tether/allow.json. `git push origin main` ran outside the jail:
[stderr]
fatal: not a git repository (or any parent up to mount point /)
Stopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).
[exit 128]
```

On `approve`, Tether adds the prefix to `.tether/allow.json`, runs the command outside the jail, gives the output to the model as a follow-up, and resumes. The prefix never asks again, in this session or a new one in the same project (a worktree session writes the project's file, not the worktree's). Any other reply (`deny`, or free text such as `no, open a PR`) tells the model the command was refused; nothing is added or run.

- **Default `escalate` list:** `git push`, `git pull`, `git fetch`, `git clone`, `git worktree`, `git config`, `gh`, `docker`. Replace it with `SandboxPolicy(escalate=(...))`; `escalate=()` turns asking off. Read-only git (`git status`, `diff`, `log`, `show`) stays in the jail with no pause.
- **The prefix is what the model asked with:** the first two words for `git`, the first word otherwise. Approving `gh` or `docker` grants the whole tool (see the hole above).
- **Only the caller approves:** `tether send`/`tether allow`, MCP `tether_send`, or `Harness.send`. A parent model's `agent send approve` counts as a refusal. A child's request shows on the child; approve it with `tether send <child_id> approve`.
- **Never offered:** commands with shell metacharacters (refused as above), git options such as `-c`/`-C`, and any command in read-only or `--no-network` sessions.
- While pending, the session JSON and MCP `tether_status` carry `"approval": {"command": ..., "prefix": ...}`.

## Known limits
- Commands run outside the jail (`--allow`) get your real `HOME`, credentials and git hooks, and git's `-c`/`--exec`/`--receive-pack` options are refused only when they appear as separate tokens or with `=`. Keep allowlisted prefixes narrow. A bare `git` entry never covers `git config`, `git remote add|set-url|set-head` or `git submodule`; those run outside only when the entry names that subcommand.
- Network is on unless you pass `--no-network`; with it on, `curl` can reach localhost services and the internet.
- There is no process-count limit by default (a fork bomb is only stopped by the timeout); opt in with `--limit procs=N` (see Resource limits above).
- Prompt injection still steers the model; the envelope only limits what an injected command can reach.

## Conformance

The sandbox conformance table lives in `tests/test_sandbox_conformance.py` as `(command, expect)` rows. The same rows are used by two tests: the unit test checks the text layer, and the e2e test in `e2e/test_sandbox_conformance.py` runs them under real bwrap. The e2e layer also needs the local Ollama reachable; the e2e suite skips otherwise.

To add a command, add one line to `TABLE`. The `expect` value means:

- `RUN`: the command must validate in both layers and exit 0 under bwrap.
- `REFUSE`: the text layer must raise `SandboxViolationError` with an `Instead:` hint.
- `MOUNT`: the text layer refuses it only in fallback mode. Under bwrap, the mounts must block it.

Run both layers from the repo root:

```bash
uv run pytest tests/test_sandbox_conformance.py -q
TETHER_E2E=1 uv run pytest e2e/test_sandbox_conformance.py -q
```

The e2e layer needs `bwrap` with user namespaces. Without them its tests are skipped, and `-rs` shows the reason.
