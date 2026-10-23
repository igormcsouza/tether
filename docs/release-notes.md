# Release Notes

## v0.2.6 (unreleased)

### Fixes

- Store: `SQLiteStore(":memory:")` no longer creates a file literally named `:memory:` in the working directory (#77). The path now maps to a temporary file outside the workspace, so every store method still shares one database.
- Sandbox: with `bwrap` active, `bash` no longer refuses commands by text for `..`, absolute paths outside the workspace, or `.env`/`.tether`/`.git/config` mentions (#125). The kernel mounts already enforce them (read-only root, hidden `$HOME`, masked secrets), so the text rules only produced false refusals such as `ls ~/..` or `cat /etc/hosts`. They remain the fallback when `bwrap` is missing, and `sudo`, `su`, disk tools, `rm -rf /`, `chmod 777`, fork bombs and `~/.ssh` stay refused in both modes.
- Sandbox: `.env.example`, `.env.sample`, `.env.template` and `.env.dist` are readable and writable; real `.env`, `.env.local`, `.env.production` stay masked and protected. Templates hold no secrets.

## v0.2.5 (2026-10-23)

Found by benchmarking the same models inside Tether and inside a plain tool loop (7 tasks, 10+ models): model idioms made the single-`act` grammar fail invisibly, and loops or oversized prompts burned steps and tokens. Closes #76, #81, #86, #89, #92 and the shell-idiom bugs #109, #110.

### Fixes

- Multiplexer: `bash -c '<cmd>'`, `bash -lc "<cmd>"` and `sh -c ...` wrappers are unwrapped to `bash <cmd>` in `normalize_cmd`, and the harness records and folds the normalized command (#109). Before, `bash` received `-c "ls"` and answered `bash: - : invalid option`, so `qwen3.5:9b` repeated the call 20+ times (code tasks 0.00).
- Multiplexer: when `bash` is enabled, an unknown first word (`ls -la`) now runs through the sandboxed `bash` tool instead of returning an error the model ignores (#109). Disabled built-ins (`web`, `mem`, ...) keep their "disabled" error. 0 prompt tokens.
- Providers: a native tool call with a name other than `act` (`edit`, `edit<|channel|>commentary`) is mapped to `<name> --k 'v'` for all three HTTP providers, so the registry answers with its JIT usage instead of a silent "(no output)" nudge (#109). `ollama` already did this; `openai` and `anthropic` dropped the call.

- Harness: the quiet `[NUDGE]` now treats `python -m unittest|pytest|doctest` and non-writing `python -c` as verification (not as a change), and `cat > f <<EOF` / any redirect as a change. Before, a model verifying with ad-hoc `python3 -c` scripts reset the counter every step and never got the hint (qwen3.5:9b used all 40 steps after solving the task) (#92).

- Harness: reading one file over varying ranges (`edit view f --lines 1:40`, `sed -n`, `cat`, `grep f`) 7 times in a row without any change is now a `cycle_stall` with a `[CYCLE DETECTED]` hint, and 4 stall warnings without an intervening change end the session `FAILED` as `Stalled: ...` (exit code 4, `failure.kind` `stalled`) instead of using every step (#92). Before, `gpt-oss-20b` looped on reads until `max_steps`.

- Context: `--context-tokens` is now enforced in three deterministic steps instead of only dropping the oldest history: fold live observations oldest-first (even inside the `--fold-after` window and the last-8-files exception), then drop the oldest call+result groups, then shrink the newest observation. The budget also adapts to the model: the assembler learns `real prompt tokens / estimate` (between 1.0 and 1.5) from the provider's usage and tightens the target, so the 4-chars/token estimate no longer lets a code-heavy prompt run past the limit. When goal, system prompt and the latest step alone exceed the budget, one warning goes to stderr (#81). Before, 8 unfolded `edit view` results reached ~24k tokens on a 16,384 budget.

- Sandbox: tools installed under `$HOME` (`~/.local/bin/uv`, nvm's `node`) are visible to `bash` and `--verify` gates again (#76). bwrap hides `/home` and `$HOME` behind a tmpfs, which also hid every `PATH` entry in them, so `uv`, `ruff` or `node` were "not found" inside the sandbox and models pip-installed tools into the workspace. Now each existing, absolute `PATH` directory under a hidden root is re-bound read-only (at most 16). Never re-exposed: the hidden roots or `$HOME` themselves, the workspace, and anything under `.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`, `.config` or `.netrc`. Secrets and the rest of `/home` stay hidden.

- Edit: a unified diff (`git diff` / `diff -u`) sent as `stdin` to `edit <path>` or `edit apply_patch` is applied as a patch (same all-or-nothing applier as `*** Begin Patch`). Before, the verbless `edit <path>` rule turned any stdin into a whole-file `write`, so `gemma4:e4b` replaced `cli.py` with the diff text and called `done` (bench task `focus`: 0.0, now 1.0 on 2/2 trials) (#86).

- Context: `mem recall` results are no longer folded back into a tombstone (#86). The recalled output of `obs_1` was itself folded two turns later, so GLM-5.3 chased `mem recall obs_3`, `obs_4`, ... for 10 steps (27 steps for a one-function edit; 10 to 11 steps after). Recalls were asked for explicitly and still fall under the `--context-tokens` budget.

### Features

- CLI: `tether stop <id>` sends SIGTERM to a running detached worker and marks the session `FAILED` as `Stopped by user.` (exit 5 on `status`/`wait`, `failure.kind` `stopped`) (#89).
- Providers: `params` on a `providers.yaml` entry and per call (`tether run --param k=v`, `Harness(params=...)`, MCP `tether_run` `params`) are merged into the request body (Ollama: `think`/`keep_alive`/`format` at request level, the rest in `options`); stored with the session, so resumed workers keep them (#112).
- Multiplexer: `register_normalizer(fn)` adds a command-quirk normalizer for every model; the built-in ones use the same list (#113).
- Dev: `bench/`, a model-in-the-loop conformance bench (six tasks, Tether / plain loop / Claude Code runners), outside the package and CI (#114).
- Edit: `apply_patch` (the Codex/V4A `*** Begin Patch` format that `gpt-oss` and other Codex-family models use natively) is accepted as `edit apply_patch` or bare `apply_patch`, with the patch in `stdin`, in a heredoc, in `cmd`, or in the stdin of `bash`. Update (context hunks, exact single match), Add and Delete File; atomic per call; the `.py` syntax warning applies. `gpt-oss-20b` issued 15+ `apply_patch` calls per run that had nowhere to go.
- Edit: the verb is optional: `edit <path>` views (no stdin), replaces (SEARCH/REPLACE blocks) or writes (other stdin); `edit --path P --line_start a --line_end b` views. `gemma4:e4b` kept sending aider-style `edit file.py` with SEARCH/REPLACE and got `unknown subcommand` (code-simple 0.00).
- Providers: optional `rpm: <n>` on a `providers.yaml` entry caps requests per minute with a sliding window kept in a lock file (`$TMPDIR/tether-rate-<uid>-<hash>.json`, override the directory with `TETHER_RATE_DIR`), so every worker, sub-agent and pipeline stage on the machine counts against one budget (#110). For keys with a hard limit such as NVIDIA's 40 req/min. Without `fcntl` the window is per process.
- Tests: golden trace `shell_wrappers` locks the new command handling.

## v0.2.4 (2026-10-21)

Dogfooding fixes: the four milestone bugs (#74 #75 #85 #88) plus the friction found by running Tether on its own backlog with `nvidia/nemotron-3-ultra-550b-a55b` (two of the fixes were first written by Tether itself from scoped briefs), and two new regression layers: golden-trace replay in CI and 54 local end-to-end scenarios.

### Features

- Tests: local end-to-end scenarios (`e2e/`, `TETHER_E2E=1 uv run pytest e2e`): the real CLI against a fault-injecting proxy in front of ollama; 54 scenarios cover the Golden Rules, lifecycle and exit codes, gates, faults (429, trickling hang, dead worker, auth), the sandbox, small-model quirks, sub-agents and pipelines, the OpenAI/Anthropic/command providers, MCP, web, skills' own tools, telemetry, `--no-network` and the context budget. Hard assertions are about tether's behaviour, so they hold for any model. See `docs/testing.md`.
- Tests: golden-trace replay (`tests/golden/`, `tests/test_golden.py`, `scripts/record_golden.py`). Recorded model steps run through the real harness and tools; the exact messages, events, tokens and files are snapshotted, so any behaviour change shows as a reviewable diff. See `docs/testing.md`.
- Edit: `edit replace <path>` also takes `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` blocks in `stdin` (the format models know from Aider): exact-text match, each SEARCH must hit exactly once, all blocks apply atomically, no line numbers. A missing final `>>>>>>> REPLACE` is tolerated (models stop after the new text); a truncated block in the middle gets a specific error. Line-numbered `--lines` still works. Motivation: `cat | sed` reads carry no line numbers, so models re-read ranges forever trying to count lines.
- Harness: deterministic one-shot `[NUDGE]` appended to the observation after 6 consecutive read-only/verification steps following a file change, reminding the model to call `done` if the task is complete (0 static prompt tokens, #74).

### Fixes

- Store: a `RUNNING` session whose worker pid no longer exists is flipped to `FAILED` (`Worker died (pid N) before finishing`) when read via `get_session`/`list_sessions`, so `status`, `list`, `wait` and `read` no longer report a killed worker as running forever (#85). A pid owned by another user counts as alive.
- Providers: `429` retries wait `Retry-After` (else 10s doubling, capped 30s) and get up to 5 attempts instead of 3 quick ones, so rate-limited hosted models (NVIDIA free tier) no longer fail the session after 3 quick attempts.
- Providers: each `post_with_retry` attempt is now bounded by a total `asyncio.wait_for(timeout)` deadline, so a trickling/stalled response cannot hang past the configured timeout; the deadline is retried like other transient errors and shows as `TimeoutError` (vs `ReadTimeout`) in the final `ProviderError` (#88).
- Harness: `max_steps` is now the absolute session ceiling. `send` on a session that used its steps extends the ceiling to `step_count + <Harness budget>`, and a session paused earlier keeps its remaining budget, so `status` never shows `step_count` above `max_steps` (e.g. `46/40`) (#75).
- Context: unfolded reads are tracked per path **and line range**. Viewing `f:55:65` used to evict the live `f:65:120` read, so the model ping-ponged between two ranges forever (found with `nvidia/nemotron-3-ultra-550b-a55b`, #69 follow-up).
- Context: the unfolded-read window is now the last 8 files (was 4); a model cycling through 5 files evicted each read just before needing it and re-read forever (#69 follow-up).
- Multiplexer: a trailing heredoc in `cmd` (`edit replace f --lines 1:1 <<'EOF'`) is now passed as `stdin` instead of failing with `requires replacement block in stdin` (never for `bash`). Found dogfooding `nvidia/nemotron-3-ultra-550b-a55b`, which never filled the `stdin` parameter in 150+ steps.
- Edit: `edit replace|write` on a `.py` file that stops parsing (e.g. a one-line replacement that lost its indentation) now ends the tool result with `WARNING: ... no longer parses: <msg> at line N. Fix it now.` so the model self-heals next step instead of discovering it ten steps later via pytest. 0 prompt tokens.

## v0.2.3 (2026-10-20)

Dogfooding fixes: the issues came from running Tether with a small model (GLM-5.3) on its own backlog.

### Features

- `tether read` now accepts `--full` (the full final result, already its default) so the `agent read <id> --full` form works on the CLI too; `--digest` still gives the compact card (#72).

### Fixes

- Verification gate errors (sandbox violation, exit 124/126/127) are now told apart from gate failures: the session fails immediately with a `Verification gate ... misconfigured: <reason>` result (exit code 3) instead of burning the 3-failure abort budget, and `tether stats` shows a `GATE_ERR` column (#33).
- `edit write` over an existing file now returns a deterministic summary (`Replaced N lines with M (X removed, Y added; first removed: ...)`) and, when the file shrank, points to `edit replace --lines a:b` (#40).
- Skills now warn (`UserWarning`, 0 prompt tokens) at load when `tools.py` defines a `@tool` not listed in the skill `tools:` (#24).
- Repeated multi-command cycles (e.g. `cat` / `sed` / `pytest`, or two alternating `sed -n` ranges) now trigger a deterministic `[CYCLE DETECTED]` nudge and a new `cycle_stall` event type, shown in `tether stats` as `CYCLES` (#39).
- HTTP providers now retry timeouts, network errors and 429/5xx twice with backoff, honour `timeout` from `providers.yaml` for all kinds, and fail with a `ProviderError` naming provider, model and timeout instead of a bare `ReadTimeout` (#70).
- Observation folding no longer makes small models re-read files in a loop: the latest read (`edit view <p>` / `bash cat|head|tail|sed -n <p>`) of each of the last 4 files stays unfolded until that path is edited (`edit write|replace`, or a bash write such as `sed -i`/`tee`) or re-read, and the fold/elision hint only mentions `mem recall` when `mem` is enabled (otherwise "re-run the command"). Static prompt prefix unchanged (#69).
- Clearer errors (#71): a provider 401/403 now fails with `ProviderError` naming the provider and the `api_key_env` / default key variable as missing or rejected (never its value), a declared `api_key_env` that is empty fails before the first request, and `unknown command` for a built-in tool that is not enabled says it is disabled and how to enable it (`--tools`, `tools=[...]`, skill `tools:`). Static prompt prefix unchanged.

## v0.2.2 (2026-10-19)

Dogfooding fixes: Tether implemented most of this release itself through the CLI and a `claude -p` provider.

### Features

- `{schema}` placeholder for `command` providers (#51): constrain output to the act schema (e.g. `claude -p --json-schema '{schema}'`); replies may be structured objects with `cmd`/`stdin`.
- `tether misses [session_id] [--model M] [--limit N] [--json]` (#53): list unparsed model replies (nudges) as fixture-ready JSONL; paste lines into `tests/fixtures/dialects.jsonl` after filling `expected`.

### Fixes

- The context budget and observation fold window are now configurable (#54): `--context-tokens` / `--fold-after` on `tether run` and `tether pipeline`, `context_tokens` / `fold_after` on `tether_run`, and per-provider keys in `providers.yaml`.
- Tool-call dialect extraction is now table-driven (#52): built-in extractors for `<tool_call>` JSON, raw JSON, `<parameter name="cmd">` blocks and text `act(...)`, extendable with `tether.register_dialect` or a `dialects:` key on `command` entries in `providers.yaml`.

## v0.2.1 (2026-10-19)

Add model backends without code.

### Features

- Declarative providers (#49): add model backends without code via `~/.tether/providers.yaml` (override with `TETHER_PROVIDERS`, never read from the workspace). Kinds `openai`, `ollama`, `anthropic` and `command` (wrap any CLI that prints JSON, run without a shell). Works in `tether run`, `tether pipeline`, the SDK and `tether mcp`. See [Declarative providers](reference/providers.md#declarative-providers).

## v0.2.0 (2026-10-19)

Tether as a subagent for the harness you already use (Claude Code, Codex, Cursor, Gemini CLI, Copilot): MCP server, JSON output and exit codes (#46). See [Use Tether Inside Your Harness](tutorial/agent-interface.md).

### Features

- **MCP server** (optional extra, `pip install "tether-sdk[mcp]"`; without it `tether mcp` warns and exits 1): `tether mcp` over stdio with `tether_run|status|wait|read|send|list|stats|query`.
- **`--json`** on `run`, `pipeline`, `status`, `list`, `read`, `wait`, `send`, `stats`; stable schema `v: 1`.
- **Exit codes**: 0 completed, 1 usage, 2 waiting for input, 3 gate failed, 4 max steps, 5 worker error. Failure text now goes to stderr.
- `Harness(output_schema=...)` / `--output-schema`, `--result-file` (JSON Schema subset enforced as a `done` gate), `tether events <id> [--follow]`.

### Fixes

- Worker errors keep the exception type and store the traceback as a `tool_error` turn (#41).
- `ollama` no longer silently substitutes an installed model on 404; it fails with the installed list. Opt back in with `TETHER_OLLAMA_FALLBACK=1` (#21).

## v0.1.4 (2026-10-18)

Security hardening from a red-team run of `ollama/qwen3.5:9b` against v0.1.3 (hidden prompt injection in a README exfiltrated a file; `docker.sock` was reachable inside `bwrap`).

### Security
- **Sandbox**: unix sockets under `/run` (including `docker.sock`, a host escape for docker-group users) are masked; `/home`, `/media`, `/mnt`, `/srv` and `/var/tmp` are hidden behind tmpfs. Previously python could read them and connect to the socket despite the command-string guard.
- **Sandbox**: secret-looking files are masked at any depth (`.env*`, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, `authorized_keys`), not only `.env*` at the workspace root. `sub/.e''nv` and `server.pem` were readable through `bash`.
- **Env**: `bash` now gets an allowlisted environment instead of a denylist. `DATABASE_URL`, `*_WEBHOOK`, `STRIPE_*` and custom `*_KEY` variables leaked before. Opt back in with `TETHER_ENV_PASSTHROUGH=A,B`.
- **Web**: `web fetch` blocks loopback, private, link-local and cloud-metadata addresses, checked on every redirect hop (`TETHER_WEB_ALLOW_PRIVATE=1` to opt out).

### Features
- **Sandbox**: optional network isolation, `tether run|pipeline --no-network` / `SandboxPolicy(network=False)` mapping to `bwrap --unshare-net`. Sub-agents and stages can only keep or narrow it; without `bwrap` it fails closed. (#23)

### Fixes
- **Sandbox**: the fallback command guard no longer rejects awk/sed/grep/perl program or pattern arguments that start with `/`. (#31)
- **Tools**: unknown names in `--tools` / `Harness(tools=...)` now raise `ValueError` (CLI prints `Error: ...`, exit 1) instead of silently loading nothing. (#22)

---

## v0.1.3 (2026-10-18)

### Fixes
- **Bash**: the `bash` tool now receives the original command text instead of a `shlex.split` then `" ".join` rebuild, so quotes survive (`sed -i 's/a b/c d/' f`, `grep -n "return list" f`, `python -c "print(1+1)"`) and pipelines, `&&` and `;` keep working. (#37)
- **History replay**: past actions are now replayed to Ollama, OpenAI-compatible and Anthropic providers as real `tool_calls` plus `tool` results (`tool_use`/`tool_result` blocks on Anthropic) instead of `act('...')` assistant text and `Observation:` user text, which small tool-calling models copied into real arguments and corrupted files. Replayed `stdin` is a real prefix (first 400 chars, then `…`) rather than a copyable `<N chars>` placeholder. Custom providers keep the textual form unless they set `structured_history = True`. The system prompt and tools array are unchanged. (#38)

### Docs
- New runnable example `examples/course/` (a plan, research and write pipeline on small local models), used as the running example across the tutorial, and a new Troubleshooting page (symptom, cause, fix, known limitations). Documents `@tool` argument parsing, the `tools.py` plus `tools:` requirement, gate and pipeline practices, observation-folding workarounds, Ollama in Docker, and the awk/sed sandbox false positive.

---

## v0.1.2 (2026-10-18)

### Fixes
- **`@tool` argument parsing**: extra unquoted words now join into the last positional `str` parameter even when later parameters are optional non-`str` (`yt-search arquitetura em camadas` with `def yt_search(query: str, limit: int = 3)`); later optionals are set via `--flag`. `*args: str` parameters now receive the words splatted instead of failing with `unexpected keyword argument`.
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
