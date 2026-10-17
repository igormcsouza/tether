# Release Notes

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
