# tether

**Tether** is a general-purpose, headless-first **LLM-Native Micro-Harness** in Python (`3.12+`) built to orchestrate both Small Language Models (`ollama/qwen3.5:9b`, `ollama/gemma4:e4b`) and frontier models (`Anthropic Claude`, `OpenAI GPT`, `OpenRouter`, `vLLM`) with **under 150 tokens of fixed prompt framing**.

Most agent frameworks drown small models in 3,000–8,000 tokens of nested JSON tool schemas and unbounded append-only transcripts before the model emits a single token. Tether flips this architecture:

- **One Action Primitive (`act`)**: Every tool call—built-in or custom—routes through a single POSIX-style command multiplexer `act(cmd: str, stdin: str | None = None)`.
- **Zero Default Tool Bloat**: By default, zero optional tools are loaded. Only the mandatory `done` termination command is active until you opt in via `--tools`, `Harness(tools=[...])`, or a Skill.
- **Progressive `--help` Disclosure**: The system prompt lists only a 1-line index per enabled tool (`<= 12 tokens`). Full usage signatures (`<= 60 tokens`) are revealed Just-In-Time (JIT) when the agent runs `<cmd> --help` or makes a syntax mistake.
- **Bounded L1 Context + SQLite FTS5 RAG**: Active observations are capped with Head+Tail elision and folded into 1-line tombstones after $K=2$ turns, while every raw output is indexed into `.tether/tether.db` (SQLite WAL + FTS5 BM25) for sub-millisecond recall.

---

## Install

Requires Python 3.12+.

=== "pip"

    ```sh
    pip install tether-sdk
    ```

=== "uv"

    ```sh
    uv add tether-sdk
    ```

---

## Quickstart

=== "CLI (Foreground & Headless)"

    ```sh
    # Zero-tool reasoning with a local 9B model (defaults to ollama/qwen3.5:9b)
    tether "Explain the CAP theorem in 3 bullet points"

    # Opt-in to web search and memory tools
    tether --tools web,mem "Research 2026 solid-state battery breakthroughs"

    # Spawn a detached background session and query its findings via BM25 RAG
    SESSION_ID=$(tether run --headless --tools web,mem "Compare SQLite WAL vs rollback journal")
    tether wait "$SESSION_ID"
    tether query "$SESSION_ID" "concurrency readers writers"
    ```

=== "Python SDK (`@tool` & `Harness`)"

    ```python
    import asyncio
    from typing import Literal
    from tether import Harness, tool


    @tool(description="Update customer subscription tier")
    def update_tier(
        customer_id: int,
        tier: Literal["free", "pro", "enterprise"] = "pro",
        stdin: str | None = None,
    ) -> str:
        """Update customer tier with an optional multi-line audit note via stdin."""
        return f"Updated #{customer_id} to {tier} (note={stdin or 'none'})"


    async def main() -> None:
        harness = Harness(
            model="ollama/qwen3.5:9b",
            tools=[update_tier, "mem"],
        )
        session = await harness.run(
            "Upgrade customer 1042 to enterprise and include a brief audit justification."
        )
        print(session.result)


    if __name__ == "__main__":
        asyncio.run(main())
    ```

---

## Why Tether?

| Dimension | Traditional Agent Frameworks | Tether Micro-Harness |
|---|---|---|
| **Base Prompt + Schema Overhead** | 3,000 – 8,000+ tokens (15–30 JSON schemas) | **< 150 tokens** (`act` primitive + 1-line index) |
| **KV-Cache Prefix Reuse** | Broken by dynamic tool injection & scratchpad edits | **100% Immutable Prefix** across every turn |
| **Observation Memory** | Append-only transcript (context blowup on step 4+) | **Head+Tail L1 Elision + $K$-Turn Folding + SQLite FTS5 BM25** |
| **Sub-Agent Coordination** | Dumps child's 15k-token transcript into parent | **~50-token Digest + `agent query` BM25 RAG** |
| **Security Boundary** | Prompt-level "please don't touch `.env`" | **Deterministic OS Sandbox (`bwrap` / workspace jail / env scrub)** |

---

## What can I do?

| I want to... | Go to |
|---|---|
| run interactive or detached headless agent sessions from the terminal | [CLI and Headless Sessions](tutorial/cli-and-headless.md) |
| embed Tether in Python and expose `@tool` functions with zero JSON boilerplate | [Python SDK and Custom Tools](tutorial/sdk-and-custom-tools.md) |
| use `bash`, `edit`, `web`, `mem`, or `done` | [Built-in Tools](tutorial/built-in-tools.md) |
| package domain instructions, model defaults, and tools into reusable skills | [Progressive Skills](tutorial/skills.md) |
| spawn parallel sub-agents and query their findings via BM25 RAG | [Async Multi-Agent Orchestration](tutorial/multi-agent.md) |
| configure `workspace-write` or `read-only` sandboxes and Linux `bwrap` | [Security and Sandbox](tutorial/security-and-sandbox.md) |
| understand the academic literature and L1/L2 memory architecture | [Architecture and Literature](architecture.md) |
| register a custom model gateway or transport | [Extending Tether](extending.md) |
| see real-world token & wall-clock benchmarks (8B local vs Sonnet vs Claude Code) | [Benchmark Evaluation](benchmarks.md) |
| look up a class or function signature | [API Reference](reference/index.md) |
