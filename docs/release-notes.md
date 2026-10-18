# Release Notes

## Unreleased (v0.1.2)

### Fixes
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
