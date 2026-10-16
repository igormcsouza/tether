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

---

## 2. The Golden Rules (Non-Negotiable Invariants)

### Rule 1: Static Prefix & KV-Cache Immutability
- **NEVER** dynamically mutate the system prompt prefix or the JSON `tools` array sent to the model provider mid-session.
- Local inference engines (`Ollama`, `llama.cpp`, `vLLM`) rely on exact prefix matching for KV-cache reuse.

### Rule 2: The Single Action Primitive (`act`) & Zero Default Tool Bloat
- Tether exposes **only one JSON tool schema** to the LLM: `act(cmd: str, stdin: str | None = None)`.
- **By default, no optional tools are loaded**—only the mandatory `done` termination command is active unless the caller explicitly loads tools via CLI (`--tools web,bash` or `--tools all`), SDK (`tools=[...]`), or a Skill (`tools: [...]` in YAML frontmatter).
- Multiline payloads (file contents, code patches, final markdown reports, scripts) **must** be passed via `stdin` rather than complex shell-escaped strings inside `cmd`.

### Rule 3: Explicit Termination (`act("done", stdin="...")`)
- Sessions do **not** terminate simply because the model emitted a text response without a tool call (small 9B models frequently "think out loud" before acting).
- A task only completes when the agent explicitly calls `act("done", stdin="<final deliverable>")` (or `act("done '<short answer>'")`), or hits `max_steps`.
- If the model emits plain text without calling `act`, the harness appends a brief deterministic nudge reminding it to either execute a command or call `done`.

### Rule 4: Progressive `--help` (JIT Schema Disclosure)
- The system prompt lists at most **1 line per enabled tool namespace** (`<name> : <short summary>`, target **≤ 12 tokens per entry**).
- Full parameter signatures, defaults, and docstrings are revealed **Just-In-Time (JIT)** when:
  1. The model explicitly runs `<cmd> --help`, OR
  2. The model invokes `<cmd>` with missing/invalid arguments (self-healing error response, never an unhandled Python exception).
- Auto-generated `--help` output must remain ultra-compact (**≤ 60 tokens** per command).

### Rule 5: Ephemeral Observation Folding
- Raw tool outputs (`bash` stdout/stderr, `web` page contents, `--help` outputs) are stored in full inside SQLite (`observations` table) and kept in the active LLM prompt for $K$ turns (default $K = 2$).
- After $K$ turns, the `ContextAssembler` deterministically folds old observations into a 1-line tombstone:
  ```text
  [obs_3 folded: `web fetch https://...` (3,420 chars) | use `mem recall obs_3` to expand]
  ```

### Rule 6: Zero Framework Bloat
- **Do NOT add heavy dependencies** like `langchain`, `llamaindex`, `crewai`, `litellm`, or vendor SDKs (`openai`, `anthropic`).
- Use Python standard library (`asyncio`, `sqlite3`, `shlex`, `inspect`, `dataclasses`, `typing`, `argparse`, `subprocess`) + ultra-lightweight essentials (`httpx`, `pyyaml`).

---

## 3. `v0` Architecture & Module Specifications

```text
src/tether/
├── __init__.py          # Public SDK exports: Harness, Session, Skill, tool
├── cli.py               # Headless-capable CLI: `tether run|status|read|send|list|wait`
├── harness.py           # Control Plane: bounded agent loop, SQLite inbox polling, worker spawn
├── store.py             # SQLite WAL persistence (.tether/tether.db): sessions, turns, inbox, obs
├── multiplexer.py       # Action Plane: `act(cmd, stdin)` parser, command registry, JIT --help
├── decorator.py         # `@tool` introspection: converts Python type hints + docstrings to CLI specs
├── context.py           # State Plane: ContextAssembler, EphemeralFolder, token estimator
├── skills.py            # Skill loader: Markdown + YAML frontmatter + optional sibling `tools.py`
├── providers/
│   ├── base.py          # Abstract async ModelProvider protocol (`generate(messages, tools)`)
│   ├── ollama.py        # Native Ollama `/api/chat` httpx adapter (`num_ctx`, `keep_alive`)
│   ├── openai.py        # OpenAI-compatible `/v1/chat/completions` httpx adapter (GPT, vLLM, Groq, OpenRouter)
│   └── anthropic.py     # Native Anthropic `/v1/messages` httpx adapter (Claude)
└── tools/
    ├── done.py          # Mandatory explicit completion command (`done`)
    ├── bash.py          # Workspace-bounded, timeout-guarded shell execution
    ├── web.py           # Zero-config DuckDuckGo Lite httpx search (+ Brave/Tavily/SearXNG env override) & reader
    ├── edit.py          # Token-efficient file viewing (`view`) & stdin patching (`write`, `replace`)
    ├── mem.py           # Working scratchpad (`pin`/`unpin`) & folded observation retrieval (`recall`)
    └── agent.py         # Async multi-agent orchestration (`spawn`, `status`, `wait`, `read`, `send`)
```

### Key Subsystem Contracts

#### A. SQLite WAL State Store (`store.py`) & Headless Execution (`cli.py` / `harness.py`)
- Default DB path: `.tether/tether.db` (configurable via `TETHER_DB` or `Harness(db_path=...)`) with `PRAGMA journal_mode=WAL;`.
- Tables:
  - `sessions`: `id`, `parent_id`, `status` (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`), `model`, `skill`, `tools_json`, `goal`, `result`, `step_count`, `max_steps`, `peak_tokens`, `pid`, `created_at`, `updated_at`.
  - `turns`: `id`, `session_id`, `step`, `role`, `content`, `tool_cmd`, `tool_stdin`, `obs_id`, `created_at`.
  - `observations`: `id`, `session_id`, `step`, `cmd`, `raw_output`, `summary`, `char_len`.
  - `pins`: `session_id`, `key`, `value`.
  - `inbox`: `id`, `session_id`, `message`, `consumed` (`0` or `1`), `created_at`.
- **Headless Worker & Live `send` Contract:**
  - `tether run --headless ...` creates the session row in SQLite and spawns `python -m tether.cli _worker <session_id>` via `subprocess.Popen(..., start_new_session=True)`, printing `<session_id>` immediately to stdout.
  - Before each step, the running worker queries `inbox WHERE session_id = ? AND consumed = 0` and injects any new user/parent messages into the conversation.
  - If `tether send <session_id> "msg"` (or `agent send`) is called when the session is `COMPLETED` or `FAILED`, it inserts the message into `inbox`, sets status back to `RUNNING`, and spawns/resumes the worker from the persisted SQLite state.

#### B. Always-Async Sub-Agent Tool (`tools/agent.py`)
- Sub-agents share the same `.tether/tether.db` with `parent_id` set to the caller's `session_id`:
  - `agent spawn [--skill <name>] [--model <m>] [--tools <t1,t2>] <goal>` $\rightarrow$ spawns a detached headless session and immediately returns `ses_<id>`.
  - `agent status <id>` $\rightarrow$ returns 1-line status, step count, and last command.
  - `agent wait <id1> [id2 ...]` $\rightarrow$ asynchronously polls SQLite until the specified child session(s) finish and returns their final `result`.
  - `agent read <id>` $\rightarrow$ reads the child session's final `result` (or recent steps if still running).
  - `agent send <id> <message>` $\rightarrow$ queues a message into the child session's inbox (or resumes it if completed).

#### C. Skills System (`skills.py`)
- Discovers skills in `./skills/` and `~/.tether/skills/`.
- Supports either `skills/<name>.md` or `skills/<name>/SKILL.md` with YAML frontmatter:
  ```yaml
  ---
  name: researcher
  description: Fast web research and synthesis
  model: ollama/qwen3.5:9b
  tools: [web, mem]
  ---
  ```
- If `skills/<name>/tools.py` exists, any `@tool`-decorated functions inside it are automatically registered into the session's multiplexer when the skill is loaded.

#### D. 3 Thin `httpx` Model Providers (`providers/`)
- Model identifier format: `<provider>/<model_name>` (e.g., `ollama/qwen3.5:9b`, `openai/gpt-4o-mini`, `anthropic/claude-3-7-sonnet-latest`).
- If no provider prefix is given, defaults to `ollama/<model>`.
- Environment variables:
  - `OLLAMA_HOST` (default `http://localhost:11434`)
  - `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1` — works with OpenRouter, vLLM, Groq, etc.)
  - `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` (default `https://api.anthropic.com`)

---

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
uv run mypy src/
```

---

## 5. Engineering & Testing Standards for Agents

1. **Token Budget Assertions in Tests:**
   - Every core feature test must assert that prompt framing and `--help` outputs stay within strict character/token budgets.
   - Base system prompt + `act` tool schema + `done` index line must consume **< 150 tokens total**.
2. **Async-First Design:**
   - All model calls and I/O-bound tool executions must be `async`/`await` native, while seamlessly wrapping synchronous user `@tool` functions.
3. **Graceful Degradation on 9B Hallucinations:**
   - Small models occasionally emit `cmd` with minor quirks (e.g., leading `$`, wrapping backticks, or calling a tool name directly instead of `act`). The multiplexer must normalize trivial syntax quirks deterministically before failing.
4. **Documentation Integrity:**
   - Keep `README.md` and `AGENTS.md` synchronized whenever architectural interfaces or built-in tool signatures change.
