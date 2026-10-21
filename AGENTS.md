# AGENTS.md — Tether Architectural & Engineering Guide

This document is the authoritative specification for AI coding agents and human contributors working on **Tether**. Read this file before planning, designing, or modifying any code in this repository.

---

## 1. Mission & Core Philosophy

**Tether** is a general-purpose, headless-first **LLM-Native Micro-Harness** written in Python (`3.12+`), designed to orchestrate both Small Language Models (SLMs like **`ollama/qwen3.5:9b`**) and frontier models (`Claude`, `GPT`, `OpenRouter`, `vLLM`) with minimal context overhead.

Most agent frameworks drown small models in thousands of tokens of JSON schemas and raw tool outputs. Tether flips this model: **it loads zero optional tools by default, keeps fixed framing overhead under 150 tokens, and reserves the context window for business logic.**

### Architectural Grounding: Maia et al. (2026)
Tether implements the architectural principles from *"LLM-Native Applications as a Paradigm for AI-Driven Software Architecture"* (Maia et al., 2026):
1. **Probabilistic Core, Deterministic Envelope:** The LLM is the central reasoning kernel, while tool routing, CLI argument parsing, context eviction, SQLite state transitions, and task termination (`done`) are strictly deterministic.
2. **Explicit Context Governance:** Context is treated as a bounded L1 working memory backed by an ACID SQLite store (`.tether/tether.db` in WAL mode)—never an unbounded append-only transcript.
3. **First-Class AI Quality Attributes:** Every change must be evaluated against **Token Economy**, **KV-Cache Prefix Immutability**, **Self-Healing Probabilistic Execution**, and **Observability**.

### Philosophy Gate (every issue, PR and review is judged against this)
Tether stays **lightweight, reliable, extensible, model-agnostic, easy to use, resourceful and a token saver**. A change that fails any line below is rejected or reworked, however useful it looks:
1. **Lightweight:** no new heavy dependency (Rule 7); prefer stdlib and existing modules over new ones; no code for hypothetical needs.
2. **Token saver:** no growth of the static prompt (< 150 tokens, Rule 1/4); new per-turn prompt content must be bounded and justified with a token-budget test.
3. **Reliable:** failures self-heal or fail loudly with an actionable message, never hang or crash silently; the deterministic envelope (loop, SQLite, sandbox, `done`) never relies on the LLM.
4. **Extensible:** new behaviour comes through providers, skills, `@tool` or config, not hardcoded special cases in the harness core.
5. **Model-agnostic:** no behaviour tied to one vendor or model; small local models and frontier models take the same code path.
6. **Easy to use:** zero-config defaults, short CLI/SDK surface, errors that say what to do next, docs in the same PR (5.4).
7. **Resourceful:** reuse existing primitives (`act`, SQLite store, FTS5 recall) before adding a new one.

Reviewers and the Team Leader cite the failing line when they reject a change.

---

## 2. The Golden Rules (Non-Negotiable Invariants)

### Rule 1: Static Prefix & KV-Cache Immutability
- **NEVER** dynamically mutate the system prompt prefix or the JSON `tools` array sent to the model provider mid-session.
- Local inference engines (`Ollama`, `llama.cpp`, `vLLM`) rely on exact prefix matching for KV-cache reuse.

### Rule 2: The Single Action Primitive (`act`) & Zero Default Tool Bloat
- Tether exposes **only one JSON tool schema** to the LLM: `act(cmd: str, stdin: str | None = None)`.
- **By default, no optional tools are loaded**—only the mandatory `done` termination command is active unless the caller explicitly loads tools via CLI (`--tools web,bash` or `--tools all`), SDK (`tools=[...]`), or a Skill (`tools: [...]` in YAML frontmatter).
- Multiline payloads (file contents, code patches, final markdown reports, scripts) **must** be passed via `stdin` rather than complex shell-escaped strings inside `cmd`.

### Rule 3: Explicit Termination (`act("done", stdin="...")`), Interactive Inquiry (`done --ask`), & Pre-`done` Verification Gates
- Sessions do **not** terminate simply because the model emitted a text response without a tool call (small 9B models frequently "think out loud" before acting).
- A task only completes when the agent explicitly calls `act("done", stdin="<final deliverable>")` (or `act("done '<short answer>'")`), pauses for human/parent input via `act("done --ask", stdin="<question>")` (transitioning the session to `WAITING_INPUT` and releasing the worker process until resumed via `send`), or hits `max_steps`.
- If the model emits plain text without calling `act`, the harness appends a brief deterministic nudge reminding it to either execute a command or call `done`.
- When `verify` gate commands are configured (via `Harness(verify=[...])`, CLI `--verify`, or Skill YAML `verify: [...]`), `Harness.execute_session` deterministically executes each command inside the session's `SandboxPolicy` before allowing `done` to transition to `COMPLETED` (consuming 0 static prompt tokens until a gate fails). A gate that errors instead of failing (sandbox violation, exit 124/126/127) ends the session `FAILED` at once as `gate_error` ("gate misconfigured"), without counting toward the consecutive-failure abort.

### Rule 4: Progressive `--help` (JIT Schema Disclosure)
- The system prompt lists at most **1 line per enabled tool namespace** (`<name> : <short summary>`, target **≤ 12 tokens per entry**).
- Full parameter signatures, defaults, and docstrings are revealed **Just-In-Time (JIT)** when:
  1. The model explicitly runs `<cmd> --help`, OR
  2. The model invokes `<cmd>` with missing/invalid arguments (self-healing error response, never an unhandled Python exception).
  3. The model invokes a built-in tool that is not enabled: the error says it is disabled, lists the enabled tools and how to enable more (error responses are history, never prefix).
- Auto-generated `--help` output must remain ultra-compact (**≤ 60 tokens** per command).

### Rule 5: Ephemeral Observation Folding
- Raw tool outputs (`bash` stdout/stderr, `web` page contents, `--help` outputs) are stored in full inside SQLite (`observations` table) and kept in the active LLM prompt for $K$ turns (default $K = 2$).
- After $K$ turns, the `ContextAssembler` deterministically folds old observations into a 1-line tombstone:
  ```text
  [obs_3 folded: `web fetch https://...` (3,420 chars) | use `mem recall obs_3` to expand]
  ```
- Exception: the latest read of each of the last 8 files (`edit view <p>`, `bash cat/head/tail/sed -n <p>`; paths normalized against the workspace) is not folded until `<p>` is edited (`edit write|replace`, or any other bash command naming it: `sed -i`, `tee`, redirects, `python -c`) or re-read. The 2,400-char head+tail elision still applies, and the hard context budget remains #81. The `mem recall` hint is shown only when `mem` is enabled (else "re-run the command").
- History is replayed as structured `tool_calls` + `tool` results (providers with `structured_history = True`; textual `act('...')` form only as fallback), with `stdin` replayed as a real 400-char prefix, never a `<N chars>` placeholder. A call and its result are trimmed together.

### Rule 6: Deterministic Security Envelope (Never Trust the LLM for Safety)
- Safety boundaries around `bash` and `edit` are enforced **deterministically by `sandbox.py` and the OS kernel**, never by system prompt instructions.
- Default profile is `workspace-write`:
  - All `edit` and `bash` paths are canonicalized (`Path.resolve()`) and confined to `workspace_root`.
  - Sensitive files/directories (`.env*`, `.git/config`, `.git/hooks`, `~/.ssh`, `.tether/`) are deterministically protected from mutation or read exfiltration.
  - `bash` subprocesses get an allowlisted environment only (secrets with any name are dropped; opt-in via `TETHER_ENV_PASSTHROUGH`). `web fetch` blocks loopback/private/metadata addresses (SSRF guard). `SandboxPolicy(network=False)` / `--no-network` adds `--unshare-net` (fails closed without `bwrap`; children can only narrow it).
  - On Linux, `bash` automatically uses **`bwrap` (Bubblewrap) / `unshare`** when available (read-only `/`, hidden `/home` and `/var/tmp` tmpfs, `/run` unix sockets such as `docker.sock` masked, read-write bind on `workspace_root` with secret-looking files at any depth (`.env*`, `*.pem`, `*.key`, ...), `.tether/`, `.git/config` and `.git/hooks` masked at the mount level, `PR_SET_NO_NEW_PRIVS`), falling back to a strict deterministic command allowlist/denylist (`rm -rf /`, `sudo`, `dd`, `mkfs`, `chmod 777`, etc. blocked).
  - Sub-agents spawned via `agent spawn` strictly inherit or narrow their parent session's `SandboxPolicy` (no privilege escalation).

### Rule 7: Zero Framework Bloat
- **Do NOT add heavy dependencies** like `langchain`, `llamaindex`, `crewai`, `litellm`, `chromadb`, or vendor SDKs (`openai`, `anthropic`).
- Use Python standard library (`asyncio`, `sqlite3` with FTS5, `shlex`, `inspect`, `dataclasses`, `typing`, `argparse`, `subprocess`) + ultra-lightweight essentials (`httpx`, `pyyaml`).

---

## 3. `v0` Architecture & Module Specifications

```text
tether/
├── __init__.py          # Public SDK exports: Harness, Pipeline, Session, Skill, SandboxPolicy, tool
├── cli.py               # Headless-capable CLI: `tether run|pipeline|status|read|query|send|list|wait|stats|retro|events|misses|mcp` (`--json` + documented exit codes)
├── harness.py           # Control Plane: bounded agent loop, pipelines, SQLite inbox, worker spawn
├── pipeline.py          # Workflow Plane: declarative multi-stage YAML pipelines & model routing
├── api.py               # Agent-facing JSON session view, exit codes, events (`--json`)
├── mcp.py               # Optional (`tether-sdk[mcp]`) stdio MCP server (`tether mcp`): tether_run/status/wait/read/send/list/stats/query
├── schema.py            # JSON Schema subset validator for `--output-schema` (a `done` gate)
├── retro.py             # Offline post-mortem: friction trace -> ≤2 Learned Rules (`tether retro`)
├── store.py             # SQLite WAL + FTS5 RAG (.tether/tether.db): sessions, turns, inbox, obs, chunks_fts
├── sandbox.py           # Security Plane: workspace-write jail, env scrubbing, Linux bwrap/unshare
├── multiplexer.py       # Action Plane: `act(cmd, stdin)` parser, command registry, JIT --help
├── decorator.py         # `@tool` introspection: converts Python type hints + docstrings to CLI specs
├── context.py           # State Plane: ContextAssembler, EphemeralFolder, token estimator
├── skills.py            # Skill loader: Markdown + YAML frontmatter + optional sibling `tools.py` (its tools must be listed in `tools:`)
├── providers/
│   ├── base.py          # Abstract async ModelProvider protocol (`generate(messages, tools)`)
│   ├── ollama.py        # Native Ollama `/api/chat` httpx adapter (`num_ctx`, `keep_alive`)
│   ├── openai.py        # OpenAI-compatible `/v1/chat/completions` httpx adapter (GPT, vLLM, Groq, OpenRouter)
│   └── anthropic.py     # Native Anthropic `/v1/messages` httpx adapter (Claude)
└── tools/
    ├── done.py          # Mandatory explicit completion command (`done`)
    ├── bash.py          # Kernel-sandboxed, env-scrubbed, workspace-bounded shell execution
    ├── web.py           # Zero-config DuckDuckGo Lite httpx search (+ Brave/Tavily/SearXNG env override) & reader
    ├── edit.py          # Workspace-jailed file viewing (`view`) & stdin patching (`write`, `replace`)
    ├── mem.py           # Working scratchpad (`pin`/`unpin`), FTS5 search (`search`), & recall (`recall`)
    └── agent.py         # Async multi-agent orchestration (`spawn`, `status`, `wait`, `query`, `read`, `send`)
```

### Key Subsystem Contracts

#### A. SQLite WAL State + FTS5 RAG Store (`store.py`) & Headless Execution (`cli.py` / `harness.py`)
- Default DB path: `.tether/tether.db` (configurable via `TETHER_DB` or `Harness(db_path=...)`) with `PRAGMA journal_mode=WAL;`.
- Tables:
  - `sessions`: `id`, `parent_id`, `status` (`PENDING`, `RUNNING`, `WAITING_INPUT`, `COMPLETED`, `FAILED`), `model`, `skill`, `tools_json`, `sandbox_json`, `goal`, `result`, `step_count`, `max_steps`, `peak_tokens`, `total_prompt_tokens`, `total_completion_tokens`, `pid`, `created_at`, `updated_at`.
  - `turns`: `id`, `session_id`, `step`, `role`, `content`, `tool_cmd`, `tool_stdin`, `obs_id`, `prompt_tokens`, `completion_tokens`, `duration_ms`, `event_type` (`ok` | `nudge` | `loop_stall` | `cycle_stall` | `syntax_error` | `tool_error` | `gate_fail` | `gate_error` | `completed`), `created_at`.
  - `observations`: `id`, `session_id`, `step`, `cmd`, `raw_output`, `summary`, `char_len`.
  - `chunks_fts` *(SQLite FTS5 Virtual Table)*: `session_id`, `source_type` (`result` | `observation` | `pin`), `source_id`, `chunk_index`, `content` — automatically indexes ~150-token paragraph/heading chunks of all observations, pins, and final `done` deliverables for sub-millisecond BM25 RAG (including cross-session project search via `mem search --project <query>`).
  - `pins`: `session_id`, `key`, `value` (supports session-scoped working memory and workspace-wide semantic facts under `GLOBAL_SESSION_ID = "__project__"` via `mem pin --project <key> <val>`).
  - `inbox`: `id`, `session_id`, `message`, `consumed` (`0` or `1`), `created_at`.
- **Agent-to-Agent Interface (`api.py`, `mcp.py`):** `--json` outputs (schema `v: 1`), exit codes `0` completed / `1` usage / `2` waiting / `3` gate / `4` max steps / `5` worker error, failure text on stderr, `--result-file`, `--output-schema`, `tether events`. `tether mcp` serves the same JSON over stdio and requires the optional `tether-sdk[mcp]` extra (official `mcp` SDK, imported lazily so core stays dependency-light; Rule 7 allows it as an extra only); its sandbox is always rooted at `--workspace` and callers can only narrow it. Details: `docs/reference/agent-interface.md`.
- **Telemetry & Failure-Mode Inspector (`tether stats`):**
  - `tether stats [--model <m>] [--skill <s>] [--limit <n>]` aggregates per-model pass rates, cumulative token economy (`total_prompt_tokens + total_completion_tokens`), step latency, and self-healing ACI friction (`nudge`, `loop_stall`, `cycle_stall`, `syntax_error`, `tool_error`, `gate_fail`, `gate_error`), plus a top-offenders breakdown by tool command.
- **Post-Mortem Distillation (`tether retro <session_id> [--apply] [--model <m>]`):** offline only (never mutates a live prompt). `store.extract_friction_trace` pulls `inbox` corrections and `loop_stall`/`cycle_stall`/`syntax_error`/`tool_error`/`gate_fail`/`gate_error` turns (+ the fixing command); one bounded LLM pass yields ≤2 rules (≤30 tokens each, deduped against existing rules). Prints a unified diff of `SKILL.md`; `--apply` appends under `## Learned Rules` (or pins to project memory when no skill was used).
- **Headless Worker & Live `send` Contract:**
  - `max_steps` is the absolute session ceiling. `send` on a session that used its steps extends it to `step_count + <Harness budget>` (a session paused earlier keeps its remaining budget), so `step_count` never exceeds `max_steps` (#75).
  - `SQLiteStore.get_session`/`list_sessions` reap dead workers: a `RUNNING` session whose stored `pid` is gone becomes `FAILED` with `Worker died (pid N) before finishing` (#85).
  - `tether run --headless ...` creates the session row in SQLite and spawns `python -m tether.cli _worker <session_id>` via `subprocess.Popen(..., start_new_session=True)`, printing `<session_id>` immediately to stdout.
  - Before each step, the running worker queries `inbox WHERE session_id = ? AND consumed = 0` and injects any new user/parent messages into the conversation.
  - If `tether send <session_id> "msg"` (or `agent send`) is called when the session is `WAITING_INPUT`, `COMPLETED`, or `FAILED`, it inserts the message into `inbox`, sets status back to `RUNNING`/`PENDING`, and spawns/resumes the worker from the persisted SQLite state.

#### B. Always-Async Sub-Agent Tool (`tools/agent.py`) & Deterministic Pipelines (`pipeline.py`)
- Sub-agents share the same `.tether/tether.db` with `parent_id` set to the caller's `session_id`:
  - `agent spawn [--skill <name>] [--model <m>] [--tools <t1,t2>] <goal>` $\rightarrow$ spawns a detached headless session and immediately returns `ses_<id>`.
  - `agent status <id>` $\rightarrow$ returns 1-line status, step count, and last command.
  - `agent wait <id1> [id2 ...]` $\rightarrow$ asynchronously polls SQLite until the specified child session(s) finish and returns a **compact ~50-token digest** (status, total chars/chunks, 2-line preview) so the parent's context window is never flooded.
  - `agent query <id|--all> <query> [--top 3]` $\rightarrow$ queries `chunks_fts` (BM25 ranking) across the sub-agent's final deliverable and raw observations, returning only the top-K relevant chunks (~200–300 tokens).
  - `agent read <id> [--full]` $\rightarrow$ reads the child session's digest or full `result`. The CLI `tether read <id>` prints the full result by default (`--full` accepted for parity; `--digest` for the digest).
  - `agent send <id> <message>` $\rightarrow$ queues a message into the child session's inbox (or resumes it if completed).
- **Deterministic Multi-Stage Pipelines (`tether pipeline <pipeline.yaml> "<goal>"` & `Harness.run_pipeline`):**
  - Each stage runs in its own isolated `SessionRecord` (`parent_id = pipeline_session_id`) with heterogeneous model routing (`stage.model`), stage-level `verify` gates, and strict sandbox monotonicity (`root_sandbox.attenuate(stage.sandbox)`).
  - Downstream stages receive a compact ~50-token digest of upstream stages plus automatic `agent query` / `agent read` access to upstream `chunks_fts` deliverables.

#### C. Skills System (`skills.py`)
- Discovers skills in `./skills/` and `~/.tether/skills/`.
- Supports either `skills/<name>.md` or `skills/<name>/SKILL.md` with YAML frontmatter:
  ```yaml
  ---
  name: researcher
  description: Fast web research and synthesis
  model: ollama/qwen3.5:9b
  tools: [web, mem]
  verify:
    - pytest -q
  ---
  ```
- If `skills/<name>/tools.py` exists, any `@tool`-decorated functions inside it are loaded with the skill and registered into the session's multiplexer when their name is also listed in the skill's `tools:` (otherwise: `unknown command`). A skill's own custom tools are opt-in like any other, so they must be listed in `tools:`; loading a skill whose `tools.py` defines an unlisted `@tool` emits a `UserWarning` (0 prompt tokens).

#### D. 3 Thin `httpx` Model Providers & SDK Provider Routing (`providers/`)
- Model identifier format: `<provider>/<model_name>` (e.g., `ollama/qwen3.5:9b`, `openai/gpt-4o-mini`, `anthropic/claude-3-7-sonnet-latest`).
- If no provider prefix is given, defaults to `ollama/<model>`.
- Custom SDK transports (e.g., internal corporate gateways, custom local runners, or test harnesses) can be injected via `Harness(provider=...)` or registered under a custom `<prefix>/<model>` via `register_provider(prefix, factory)`.
- Declarative providers: `~/.tether/providers.yaml` (override with `TETHER_PROVIDERS`, never read from the workspace) maps a model-id prefix to a `kind` (`openai`, `ollama`, `anthropic` or `command`); `claude-cli/sonnet` uses the entry `claude-cli`. The `command` kind runs `argv` directly (never through a shell) with `{model}`, `{system}` and `{conversation}` placeholders, and reads the reply and usage from JSON paths. Built-in prefixes (`ollama`, `openai`, `anthropic`, `claude`) cannot be shadowed, keys are env var names (never values), and an invalid file raises `ValueError: providers.yaml: ...`. Implementation in `tether/providers/declarative.py`; docs in `docs/reference/providers.md`.
- Environment variables:
  - `OLLAMA_HOST` (default `http://localhost:11434`); `TETHER_OLLAMA_FALLBACK=1` opts in to substituting an installed model when the requested one 404s (default: fail loudly with the installed list)
  - `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1` — works with OpenRouter, vLLM, Groq, etc.)
  - `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` (default `https://api.anthropic.com`)

---
- **Timeout/retry (#70):** `providers.yaml` `timeout` applies to every kind; HTTP providers retry timeouts/network errors/429/5xx twice (`post_with_retry` in `providers/base.py`) then raise `ProviderError` naming provider, model and timeout; each attempt is also bounded by a total `asyncio.wait_for(timeout)` deadline (#88).
- **Context config (#54):** `max_context_tokens` / `fold_observations_after` resolve as explicit argument (`--context-tokens` / `--fold-after`, MCP `context_tokens` / `fold_after`) > `providers.yaml` entry keys `context_tokens` / `fold_after` > defaults 8192 / 2.

## 4. Development Workflow & Commands

We use **`uv`** for fast, reproducible Python environment and package management.

```bash
# Install dependencies and sync environment
uv sync

# Run unit and token-budget tests
uv run pytest

# Run linter and formatter
uv run ruff check .
uv run ruff format --check .

# Run static type checking
uv run mypy tether/
```

---

## 5. Engineering & Testing Standards for Agents

1. **Token Budget Assertions in Tests:**
   - Every core feature test must assert that prompt framing and `--help` outputs stay within strict character/token budgets.
   - Base system prompt + `act` tool schema + `done` index line must consume **< 150 tokens total**.
2. **Async-First Design:**
   - All model calls and I/O-bound tool executions must be `async`/`await` native, while seamlessly wrapping synchronous user `@tool` functions.
3. **Graceful Degradation on 9B Hallucinations:**
   - Small models occasionally emit `cmd` with minor quirks (e.g., leading `$`, wrapping backticks, or calling a tool name directly instead of `act`). The multiplexer must normalize trivial syntax quirks deterministically before failing. This includes unescaping literal `\n`/`\t` in one-line `stdin` for `edit write`/`edit replace` and `done` (never `bash`), and turning a trailing shell heredoc in `cmd` (`edit write f <<'EOF' ... EOF`) into `stdin` (never for `bash`).
4. **Golden traces:** behaviour the model sees (framing, folding, nudges, tool output) is locked by `tests/golden/*.snap.json`. A PR that changes it runs `UPDATE_GOLDEN=1 pytest tests/test_golden.py` and the snapshot diff is part of the review; unrelated traces must not change. See `docs/testing.md`.
5. **Documentation Integrity:**
   - Keep `README.md` and `AGENTS.md` synchronized whenever architectural interfaces or built-in tool signatures change.
   - **Always update documentation in the same PR** when introducing a new feature, changing an existing behavior, or altering a CLI/SDK interface. This covers `README.md`, `AGENTS.md`, the MkDocs pages under `docs/` (including `docs/reference/*` for new modules), and a `docs/release-notes.md` entry. A change without matching docs is incomplete.

## Dev team specifics
- Stack: Python 3.12+, package `tether/`, tests in `tests/`, docs in `docs/` (MkDocs); `uv`, ruff, mypy
- Checks: lint `uv run ruff check . && uv run ruff format --check .`; types `uv run mypy tether/`; tests `uv run pytest --cov=tether --cov-report=term-missing --cov-fail-under=100` (CI enforces 100% coverage)
- E2E / QA: none beyond pytest; no shared single-instance resources
- Branches/commits/PRs: Conventional Commits (`feat(scope): ... (#N)`, `release: vX.Y.Z ...`); PR per task, squash-merged to `main`; docs updated in the same PR (see section 5.4)
- Delivery: PR per task
- Hard stops (ask first): force push / history rewrite
- Design docs: `AGENTS.md` sections 1-3, `docs/architecture.md`, `docs/reference/*`
- feature-context store: .claude/feature-context/
