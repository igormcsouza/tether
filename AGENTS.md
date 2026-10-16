# AGENTS.md — Tether Architectural & Engineering Guide

This document is the authoritative specification for AI coding agents and human contributors working on **Tether**. Read this file before planning, designing, or modifying any code in this repository.

---

## 1. Mission & Core Philosophy

**Tether** is a general-purpose, **LLM-Native Micro-Harness** written in Python (`3.12+`), designed to orchestrate Small Language Models (SLMs) such as **`qwen3.5:9b`** with minimal context overhead.

Most agent frameworks drown small models in thousands of tokens of JSON schemas and raw tool outputs. Tether flips this model: **the harness overhead must remain near-zero (<150 tokens of fixed system/tool framing) so the context window stays dedicated to business logic.**

### Architectural Grounding: Maia et al. (2026)
Tether implements the architectural principles from *"LLM-Native Applications as a Paradigm for AI-Driven Software Architecture"* (Maia et al., 2026):
1. **Probabilistic Core, Deterministic Envelope:** The LLM is the central reasoning kernel, but all tool routing, argument parsing, context pruning, and loop guardrails are strictly deterministic.
2. **Explicit Context Governance:** Context is treated as a bounded L1 working memory with deterministic eviction/folding policies—never an unbounded append-only transcript.
3. **First-Class AI Quality Attributes:** Every change must be evaluated against **Token Economy**, **KV-Cache Prefix Immutability**, **Self-Healing Probabilistic Execution**, and **Observability**.

---

## 2. The Golden Rules (Non-Negotiable Invariants)

### Rule 1: Static Prefix & KV-Cache Immutability
- **NEVER** dynamically mutate the system prompt prefix or the JSON `tools` array sent to the model provider between turns.
- Local inference engines (`Ollama`, `llama.cpp`, `vLLM`) rely on exact prefix matching for KV-cache reuse. Dynamic tool injection at the top of the prompt destroys per-turn latency.

### Rule 2: The Single Action Primitive (`act`)
- Tether exposes **only one JSON tool schema** to the LLM: `act(cmd: str, stdin: str | None = None)`.
- All built-in tools (`bash`, `web`, `edit`, `mem`) and user-registered domain functions (`@tether.tool`) are accessed as subcommands through `act`.
- Multiline payloads (file contents, code patches, JSON bodies, SQL queries) **must** be passed via the optional `stdin` parameter rather than complex shell-escaped strings inside `cmd`.

### Rule 3: Progressive `--help` (JIT Schema Disclosure)
- The system prompt may only list **1 line per tool namespace** (`<name> : <short summary>`, target **≤ 12 tokens per entry**).
- Full parameter signatures, defaults, and docstrings are revealed **Just-In-Time (JIT)** when:
  1. The model explicitly runs `<cmd> --help`, OR
  2. The model invokes `<cmd>` with missing/invalid arguments (self-healing error response).
- Auto-generated `--help` output must be ultra-compact (**≤ 60 tokens** per command) and human/LLM scannable.

### Rule 4: Ephemeral Observation Folding
- Raw tool outputs (`bash` stdout/stderr, `web` page contents, `--help` outputs) are **ephemeral**.
- Keep full output in the context window for $K$ turns (default $K = 1$ or $2$), then deterministically fold old observations into a single-line tombstone:
  ```text
  [folded observation #3: `web fetch https://...` -> 200 OK (3,420 chars) | use `mem recall obs_3` to expand]
  ```
- Optionally cache the full raw output in out-of-context memory (`mem`) so the model can retrieve slices if needed.

### Rule 5: Zero Framework Bloat
- **Do NOT add heavy dependencies** like `langchain`, `llamaindex`, `crewai`, or massive SDKs.
- Prefer Python standard library (`asyncio`, `shlex`, `inspect`, `dataclasses`, `typing`, `argparse`) + ultra-lightweight essentials (`httpx`, `pydantic` or `msgspec` only if strictly needed).

---

## 3. Component Architecture & Directory Layout

```text
src/tether/
├── __init__.py          # Public API exports: Harness, tool, ContextPolicy, RunResult
├── harness.py           # Control Plane: bounded agent loop, step limits, loop detection
├── multiplexer.py       # Action Plane: `act(cmd, stdin)` parser, command registry, JIT --help
├── decorator.py         # `@tool` introspection: converts Python type hints + docstrings to CLI specs
├── context.py           # State Plane: ContextAssembler, EphemeralFolder, token estimator
├── providers/
│   ├── base.py          # Abstract async ModelProvider protocol
│   ├── ollama.py        # Native Ollama /api/chat adapter (with keep_alive & num_ctx control)
│   └── openai_compat.py # OpenAI-compatible chat completions adapter (vLLM, llama.cpp, cloud)
├── tools/
│   ├── bash.py          # Sandboxed/timeout-bounded shell execution
│   ├── web.py           # Lightweight search & HTML-to-Markdown reader
│   ├── edit.py          # Token-efficient file viewing (line ranges) & stdin patching/writing
│   └── mem.py           # Working scratchpad & folded-observation retrieval
└── telemetry.py         # Operational Plane: token counters, KV-cache friendliness metrics, trace hooks
```

### Detailed Module Specifications

#### A. `decorator.py` & `multiplexer.py` (Virtual CLI Multiplexer)
- Inspects any sync or async Python function decorated with `@tool`.
- Extracts parameter names, types (`int`, `str`, `bool`, `float`, `Literal`, `list`), defaults, and whether a `stdin: str` parameter is accepted.
- Parses incoming `cmd` strings using `shlex.split(cmd, posix=True)`.
- Supports both positional and flag-based invocation (e.g., `crm upgrade 1042 --tier enterprise` or `crm upgrade --customer-id 1042 --tier enterprise`).
- On `argparse`/validation failure, **never raise an unhandled exception to the loop**; return a structured, concise usage hint:
  ```text
  Error: missing required argument `--customer-id` (int).
  Usage: crm upgrade <customer_id:int> [--tier:free|pro|enterprise='pro']
  Desc : Update customer tier.
  ```

#### B. `context.py` (Memory & Context Layer)
- Tracks three distinct memory regions in the prompt:
  1. **Immutable Prefix:** System instructions + 1-line Virtual Toolbox Index (never changes mid-run).
  2. **Pinned Domain State:** Business context, active goal, and key-value scratchpad facts (`mem pin`).
  3. **Sliding Episodic Window:** Recent turns, where observations older than `fold_after_turns` are automatically folded.

#### C. `tools/edit.py` (SLM-Friendly File Operations)
- Small models struggle with complex unified diff syntax.
- `edit` subcommands must use `stdin` cleanly:
  - `edit view <path> [--lines 1:80]` — View numbered lines.
  - `edit write <path>` (with content in `stdin`) — Create or overwrite file.
  - `edit replace <path> --lines <start>:<end>` (with replacement block in `stdin`) — Deterministic line-range replacement.

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
   - Every core feature test should assert that prompt framing and `--help` outputs stay within strict character/token budgets.
   - The base system prompt + `act` tool schema + 4 built-in tool index lines must consume **< 250 tokens total**.
2. **Async-First Design:**
   - All model calls and I/O-bound tool executions must be `async`/`await` native, while seamlessly wrapping synchronous user `@tool` functions.
3. **Graceful Degradation on 9B Hallucinations:**
   - Small models occasionally emit `cmd` with minor quirks (e.g., leading `$`, wrapping backticks, or calling a tool directly instead of `act`). The multiplexer should normalize trivial syntax quirks deterministically before failing.
4. **Documentation Integrity:**
   - Keep `README.md` and `AGENTS.md` synchronized whenever architectural interfaces or built-in tool signatures change.
