# Release Notes

## v0.2.4 (unreleased)

### Fixes

- Harness: `max_steps` is now the absolute session ceiling. `send` on a session that used its steps extends the ceiling to `step_count + <Harness budget>`, and a session paused earlier keeps its remaining budget, so `status` never shows `step_count` above `max_steps` (e.g. `46/40`) (#75).

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
