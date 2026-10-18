# CLI and Headless Sessions

The `tether` CLI is designed for both interactive developer workflows and headless shell automation. Every session is persisted in an ACID SQLite WAL database (`.tether/tether.db` by default, or overridden via `--db` / `TETHER_DB`).

## Installing the CLI from PyPI

Install the `tether-sdk` package from PyPI using `pip` or `uv` to make the `tether` command available in your shell:

=== "pip"

    ```sh
    pip install tether-sdk
    tether --version
    ```

=== "uv tool (global CLI)"

    ```sh
    uv tool install tether-sdk
    tether --version
    ```

=== "uvx (one-off execution)"

    ```sh
    uvx --from tether-sdk tether "Summarize the CAP theorem"
    ```

## Foreground Execution

When you pass a goal directly to `tether` (or `tether run`), the session runs in the foreground and prints the final deliverable when the agent calls `done`:

```sh
# Uses ollama/qwen3.5:9b by default with zero optional tools
tether "Summarize the trade-offs between B-Trees and LSM-Trees"

# Enable specific built-in tools
tether run --model ollama/qwen3.5:9b --tools bash,edit "Run pytest and fix any failing assertions"

# Or enable all built-in tools (web, bash, edit, mem, agent, skill)
tether run --tools all "Audit the repository structure and write a report"
```

## Detached Headless Sessions (`--headless`)

Passing `--headless` creates the session record in SQLite, spawns a detached background worker process (`python -m tether.cli _worker <session_id>`), and immediately prints the session ID (`ses_<hex>`) to `stdout`:

```sh
SESSION_ID=$(tether run --headless --tools web,mem "Compare PostgreSQL 17 vs SQLite WAL")
echo "Spawned background session: $SESSION_ID"
```

## Monitoring & Reading Results

While a headless worker is running—or after it finishes—you can inspect its state without blocking or flooding your terminal:

```sh
# 1-line status summary (status, step count, model, peak tokens)
tether status "$SESSION_ID"

# Block until the session completes and print a compact ~50-token digest
tether wait "$SESSION_ID"

# Read the full final deliverable
tether read "$SESSION_ID"

# Inspect the step-by-step action log
tether read "$SESSION_ID" --steps

# Run a BM25 FTS5 search over the session's observations and final result
tether query "$SESSION_ID" "write-ahead log checkpointing" --top 3

# List recent sessions in .tether/tether.db
tether list
```

## Live Inbox Injection & Auto-Resume (`tether send`)

Every session has a persistent SQLite `inbox` queue:

1. **If the session is `RUNNING`**: `tether send` enqueues your message into SQLite. Before the next step begins, the worker consumes the inbox and injects your instruction into the conversation.
2. **If the session is `COMPLETED` or `FAILED`**: `tether send` enqueues your message, resets the session status, and resumes execution with full access to its prior turns, observations, and pinned memory.

```sh
# Send a follow-up instruction and wait for the updated deliverable
tether send "$SESSION_ID" "Include a section on mmap_size performance"

# Or resume in the background without blocking
tether send --headless "$SESSION_ID" "Now export the comparison table to CSV"
```

## Waiting for input, telemetry and retro

If the agent calls `done --ask`, the session becomes `WAITING_INPUT`; `tether wait` returns and `tether send` resumes it. `tether stats` shows per-model pass rate, token cost and friction, and `tether retro <session_id>` distills a session's mistakes into at most 2 rules. See [Gates, Memory, Pipelines & Telemetry](workflows-and-telemetry.md).

## Example: Ollama in Docker

The [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course) ran against an Ollama container instead of a host install:

```sh
docker run -d --name tether-ollama --gpus all -v ollama_models:/root/.ollama \
  -p 11435:11434 ollama/ollama:0.40.0
docker exec tether-ollama ollama pull qwen3.5:9b

export OLLAMA_HOST=http://localhost:11435
tether run --model ollama/qwen3.5:9b "Say hello"
```

`OLLAMA_HOST` is read by the Ollama provider (default `http://localhost:11434`).
