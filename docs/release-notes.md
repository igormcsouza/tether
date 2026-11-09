# Release Notes

## Unreleased

### Changed

- Sandbox refusals now name the rule, what to do instead, and the flag that would permit it when one exists (#124 item 3). No change to which commands are allowed or refused.

### Added

- `tether export <id>` prints a session as a Markdown transcript (`--out FILE` to save it).
- A `--verify` gate whose program does not exist (checked for every command in a `&&`/`||`/`;`/`|` chain) now fails the session before the first model call, as a misconfigured gate (#82).
- `tether doctor` checks your setup (Ollama reachable, model pulled, bwrap, providers.yaml, session DB) and says what to fix; exit 1 when a check fails.
- `tether run --worktree` runs the session in its own git worktree on branch `tether/<id>` and commits the result there when it stops. `--worktree-from <ref>` sets the base ref and `--setup <cmd>` runs a shell command in the worktree before the model starts (outside the sandbox, not offered over MCP). See [Run a session on its own branch](guides/own-branch.md).
- `tether read <id> --thinking` prints the stored model thinking for each step. Thinking is kept for reading only and is never replayed to the model.

- `tether replay SESSION_ID` re-runs a session's goal in the current directory with its saved tools, skill, sandbox, output_schema and params, and prints the original and replay side by side (`--model`, `--max-steps`, `--json`). Verify gates are not stored, so a replay runs without them.
- `tether pipeline --resume <id>` re-runs a failed or waiting pipeline from its first unfinished stage and reuses the stages that completed (#35).
- `--max-tokens N` (CLI), `Harness(max_tokens=)` and the MCP `tether_run` argument `max_tokens` set a token budget (prompt + completion). When the budget is reached the session pauses as WAITING_INPUT (exit 2) and `send` adds the same amount again as a grant. Sessions without a budget are unchanged.
- `tether mcp`: `tether_run` accepts `workspace`, an absolute directory inside the server's workspace, so a caller working in a git worktree can root the run there; anything outside is refused (#242).
- `tether diff <session_id>` shows what a session changed in its files, against the first bytes the session saw (`--stat` for line counts). Snapshots are recorded by the harness write-tracking loop in a new `file_snapshots` table; files created by the session show as added from empty.

### Fixed
- A headless worker that dies before it starts no longer leaves its session PENDING: it is marked FAILED with `Worker died (pid N) before starting`, and the result names the worker's log (`<db dir>/workers/<id>.log`), which now keeps the worker's stdout and stderr (#271).
- `edit write` on an existing file with stdin made only of complete SEARCH/REPLACE blocks now applies them as `edit replace` instead of replacing the whole file (#267).
- `tether wait` exits 6 and prints `timed out; still RUNNING: ...` on stderr when the timeout expires (#269).
- Command provider timeouts and empty failures are retried twice before raising `ProviderError` (#268).
- Headless workers always import the installed tether, never a workspace's own tether/ package (#273).
- An empty model reply is retried. If the retry is empty too, the session stops instead of continuing with no output (#135).
- `tether run --worktree` no longer commits bytecode and tool caches (`__pycache__`, `*.pyc`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.tether/`) (#278).

## v0.2.18 (2026-11-08)

Small fixes from the v0.2.17 release check and the paasio labs: shell-style file writes work when only `edit` is enabled, `edit append` adds to a file instead of replacing it, a foreground run prints its session id at once, and a `cd` into a container path that does not exist no longer costs a step.

### Added

- `edit append <path>` adds `stdin` to the end of a file (created if missing, with a newline added when the file does not end with one). Small models assumed `edit write` appends: gemma4:e4b wrote a plan module by module and kept only the last one. The `edit` help now says `write replaces the file` and stays within 59 tokens; with `bash` off, `echo t >> f` runs as `edit append f` (#34).
- A foreground `tether run` (with or without `--json`) writes `session ses_<id>` to stderr as soon as the session is created, before the first model call. A caller that kills the run on its own timeout no longer needs `tether list` to find the id for `status`, `stop` or `send`; stdout is unchanged (#90).

### Fixed

- `cd /testbed && python3 -m unittest ...`, with a directory that does not exist, now runs the command after the `cd` in the workspace, with one line saying the `cd` was skipped. Models assume a container path; qwen3.5:9b lost a step to it in 3 of the last 6 paasio runs. A `cd` into a real directory runs as before (#79).
- `tether stats` offenders: a leading `cd <dir> &&` no longer makes `cd` the offending command (the command after it is counted), and a turn without a command shows as `(no command)` instead of `unknown` (#79).
- With `edit` enabled and `bash` not, a plain shell file write or read now runs as `edit`: `echo ok > hello.txt`, `printf 'a\nb' > f`, `cat > f << 'EOF' ... EOF` become `edit write`, and `cat f` becomes `edit view f`. Any other shell command still answers `unknown command`, now with a pointer to `edit view|write`. In the v0.2.17 release check (`--tools edit`, "Create hello.txt containing ok"), qwen3.5:9b tried `echo`, `printf`, `cat` and `ls` 10 times before writing the file at step 12 of 15. Pipes are not translated.

## v0.2.17 (2026-11-07)

When tests fail, tether now works around them on its own time: it re-runs them after each edit, traces the smallest failing test, starts fresh when an approach keeps failing, and keeps a version that nearly passes instead of throwing it away. The north star (74% on Polyglot-Python with qwen3.5:9b) moves to v0.4.0. No full Polyglot run was made for this release; the numbers below are from targeted labs.

### Added

- A repair loop around failing tests, all from the harness's own time (0 static prompt tokens, no extra model call). Once the model has run the tests, they run again after each edit and the result is appended (`[auto-test]`), so no version is typed blind. When the model reads the tests of the file it is about to write, it is asked once to say in plain words what the hardest tests call and expect (`[BEFORE WRITING]`). When the same tests fail again after a change, or only a few still fail, a runtime trace of the smallest failing test shows the calls into your code with their arguments and results. When at most 3 tests still fail, one note points to `edit replace` instead of a whole-file rewrite. On `paasio` with qwen3.5:9b (600 s cap) the mean score went from 0.63 over 3 runs to 0.94 over 5 runs, with 1 of 5 passing; the other 4 ended at the time cap with 22 to 24 of 25 tests passing (#173).

### Changed

- The north star is now 74% (50 of 68) on Polyglot-Python with qwen3.5:9b by v0.4.0, instead of 80% by v0.3.0. 74% is the share of exercises the model has already solved at least once from scratch (25 of 34), so the target is reliability: each of them passing every run. The 9 exercises it never solved are out of scope for this target (#173).
- A restart after the same tests failed 3 times is now a fresh start: the files the model changed go back to how they started, and the restart message names the failing tests instead of quoting the failed code (Olausson et al., ICLR 2024). A version that already passes all but at most 3 tests is kept instead: when later edits do not beat it, its files come back in place with a `[RESTORED]` line and the history stays (#173).
- The number of failing tests is read from the runner's summary line (`FAILED (failures=1, errors=3)`), so a test run cut by `| head` is no longer taken for a near pass (#173).

### Fixed

- `edit write hello.txt ok`, with the content typed after the path and no `stdin`, now writes `ok` instead of answering ``Error: `edit write` requires file content in `stdin` ``. qwen3.5:9b lost two steps this way creating a one-line file in the v0.2.16 smoke run. The text is taken as typed (spacing kept, one pair of surrounding quotes removed, literal `\n` unescaped); `stdin`, when given, still wins (#173).
- In `tether list`, a pipeline's own row now shows the model its stages run on instead of the harness default (`ollama/qwen3.5:9b` even when every stage set `model: local/qwen3.5:9b`). When stages use different models, the row lists them in stage order, joined with `,`. A stage with no `model:` still runs on the pipeline's default model.
- A test run piped to `head` (`python3 -m unittest ... 2>&1 | head -100`) now keeps its result. The runner prints its summary (`Ran 26 tests` / `FAILED (failures=8)`) last, so `head` cut it, and the pipe also replaced the tests' exit code with `head`'s 0: the model could not tell how many tests failed, and tether's own notes on test runs (failing test source, regressions, green-test finish) did not fire. Now tether runs the test command itself, keeps the first N lines and adds `[... K lines cut by head; the end of the output:]` with the last 6 lines and the real `[exit N]`. In the v0.2.15 Polyglot run on qwen3.5:9b, 22 of 39 failing runs had at least one test result cut this way, against 7 of 47 passing runs. On 4 of those exercises plus 2 passing controls (32k, one run each), e
... [truncated 48,068 chars by sandbox cap] ...
- **Multiplexer**: small models that send `edit write`/`edit replace` stdin or the `done` deliverable as one line with literal `\n` (and `\t`) escapes now get them unescaped deterministically (only when the stdin has no real newline). `bash` stdin and all other tools are never touched. (#26)

---

## v0.1.1 (2026-10-18)

### Fixes
- **Bash**: a command with no output now returns `[exit 0: no output] Command succeeded.` instead of a bare `[exit 0]`, which 9B models misread as failure and repeated until the loop breaker fired.
- **Docs**: new tutorial page for gates, `done --ask`, project memory, pipelines, `stats` and `retro`; added the documented-but-missing `tether --version`.

---

## v0.1.0 (2026-10-17)

### Milestone v0.1: Deterministic Control Plane
- **Pre-`done` Verification Gates**: `Harness(verify=[...])`, `--verify`, or Skill `verify:` run inside the session `SandboxPolicy` before `done` can complete a session (0 static prompt tokens until a gate fails).
- **Interruptible `WAITING_INPUT` & `done --ask`**: sessions can pause for human/parent input and resume via `tether send`.
- **Hierarchical Project Memory**: `mem pin --project` / `mem search --project` with cross-session BM25 RAG.
- **Telemetry & Failure-Mode Inspector (`tether stats`)**: per-model pass rate, token cost, step latency and ACI friction offenders.
- **Deterministic Multi-Stage Pipelines (`tether pipeline`)**: isolated stage sessions, heterogeneous model routing, monotonic sandbox attenuation, ~50-token stage handoffs.
- **Post-Mortem Distillation (`tether retro`)**: `tether retro <session_id> [--apply]` extracts a session's friction trace (inbox corrections, loop stalls, syntax/tool errors, gate failures) and distills at most 2 deduplicated rules (<= 30 tokens each) into `SKILL.md` under `## Learned Rules`, or project memory when no skill was used. Runs offline, never mutating a live prompt.

### Fixes found during release validation
- **Sandbox**: `bwrap` now really unshares PID/IPC namespaces (docs claimed it); under `bwrap`, `.env*`, `.tether/`, `.git/config` and `.git/hooks` are now masked at the kernel level. Previously only a command-string regex guarded them, so `cat .e*` or `cat $(echo .en)v` read secrets and `echo >> .git/con*` modified git config. `SSH_AUTH_SOCK`/`GPG_AGENT_INFO` are scrubbed and `/run/user` is hidden.
- **`tether stats`**: pipeline root sessions are excluded; they invented a run for the default model and double-counted stage tokens.
- **Multiplexer**: an unknown first token (e.g. a raw `echo hi > f`) now hints `bash <cmd>` when the `bash` tool is enabled; small models previously looped on the bare error.
- **CLI**: `tether pipeline` (missing file, invalid YAML, stage without `goal`) and `tether send <unknown id>` print `Error: ...` and exit 1 instead of a traceback.

---

## v0.0.3 (2026-10-17)

### Architectural & Performance Upgrades
- **Head + Tail L1 Active Observation Elision (`tether/context.py`)**: Oversized active observations (`> 2,400 chars`) are deterministically elided in L1 working memory to their first 900 chars (headers/command summary) + last 900 chars (stack trace/exit code) with a pointer to `mem recall` / `mem search`, preserving full outputs in SQLite FTS5.
- **Deterministic Loop-Stall Breaker (`tether/harness.py`)**: Consecutive identical `(cmd, stdin)` calls from small 8B/9B models are intercepted before tool execution and answered with a deterministic `[LOOP DETECTED]` recovery nudge.
- **100% KV-Cache Prefix Immutability Across Pins (`tether/context.py`, `tether/providers/anthropic.py`)**: `[PINNED MEMORY]` is attached to the tail message after window trimming so earlier turn messages remain 100% byte-identical when pins change; added Anthropic ephemeral `cache_control` breakpoints.
- **Persistent Connection Pooling & Thread-Local SQLite WAL (`tether/providers/*`, `tether/store.py`)**: Reuses persistent `httpx.AsyncClient` instances across turns and caches thread-local SQLite WAL connections with `PRAGMA temp_store=MEMORY;` and 128 MB `mmap_size`.

### Packaging, Documentation & CI
- **PyPI Trusted Publishing (`tether-sdk`)**: Published on PyPI as `tether-sdk` (`pip install tether-sdk` / `uv add tether-sdk`) with automated OIDC delivery (`.github/workflows/delivery.yml`).
- **Flattened Package Layout**: Moved `tether/` to the repository root (removing `src/`).
- **MkDocs Documentation Site**: Added full documentation, tutorials, literature review, and `mkdocstrings` API reference at `https://igormcsouza.github.io/tether/` (`.github/workflows/docs.yml`).
- **Modular Test Suite & 100% Coverage CI Gate**: Split unit tests into 20 per-module test files under `tests/` and added `.github/workflows/ci.yml` enforcing `ruff`, `mypy`, `mkdocs build --strict`, and `pytest --cov=tether --cov-fail-under=100`.

---

## v0.0.2 (2026-10-17)

### SDK Provider Extensibility & Literature Grounding
- **Custom SDK Provider Registry (`register_provider`)**: Added `register_provider(prefix, factory)` in `tether.providers` so SDK consumers can route `<prefix>/<model>` identifiers through custom gateways, local inference engines, or test transports.
- **Literature Grounding**: Documented architectural alignment with Maia et al. (2026), Wang et al. (*CodeAct*, ICML 2024), Yang et al. (*SWE-agent*, NeurIPS 2024), and Packer et al. (*MemGPT*, 2023).

---

## v0.0.1 (2026-10-16)

### Initial Release
- Single `act(cmd, stdin)` action multiplexer with `< 150` tokens of base framing overhead.
- `@tool` Python function introspection with JIT `--help` disclosure (`<= 60` tokens).
- SQLite WAL session store + FTS5 BM25 RAG (`chunks_fts`) and ephemeral $K$-turn observation folding.
- Detached headless worker execution (`tether run --headless`, `wait`, `send`, `query`, `read`, `list`).
- Always-async multi-agent orchestration (`agent spawn`, `wait`, `query`, `read`, `send`).
- Deterministic `SandboxPolicy` with workspace path confinement, secret environment scrubbing, and Linux `bwrap` isolation.
