# Built-in Tools

By default, Tether loads **only** the `done` command so pure reasoning tasks pay zero tool-schema overhead. You can enable any combination of built-in tools via `--tools` (CLI), `Harness(tools=[...])` (SDK), or `tools: [...]` (Skill frontmatter).

| Namespace | Summary Line (`<= 12 tokens`) | Purpose |
|---|---|---|
| `done` | `done : Finish task and submit final deliverable` | Mandatory explicit termination command |
| `bash` | `bash : Execute sandboxed shell command in workspace` | Kernel-sandboxed (`bwrap`), env-scrubbed shell execution |
| `edit` | `edit : View, write, or replace lines in workspace files` | Workspace-jailed file viewing and `stdin` patching |
| `web` | `web : Search the web or fetch URL as markdown` | Zero-config DuckDuckGo Lite search & HTML-to-Markdown reader |
| `mem` | `mem : Pin working facts or search folded observations` | Key-value scratchpad + SQLite FTS5 BM25 search & recall |
| `skill` | `skill : List or load specialized domain skills` | Progressive discovery and JIT loading of Skills |
| `agent` | `agent : Spawn and query async child sub-agents` | Detached multi-agent orchestration + BM25 RAG |

---

## `done` — Explicit Termination

Sessions never terminate simply because a model emitted plain text without calling a tool (small 8B/9B models frequently think out loud before acting). The agent must call `done`:

```text
act(cmd="done '42'")
act(cmd="done", stdin="# Final Report\n\nAll tests pass.")
```

## `bash` — Sandboxed Shell Execution

Executes commands inside `workspace_root` with secret environment variables scrubbed and Linux `bwrap` isolation (when available):

```text
act(cmd="bash pytest -q")
act(cmd="bash", stdin="python3 - << 'EOF'\nimport math\nprint(math.pi)\nEOF")
```

## `edit` — Workspace-Jailed File Operations

Provides deterministic line-numbered viewing and `stdin`-based writing/replacement without sed/awk quoting bugs:

```text
# View a file or a specific line range
act(cmd="edit view tether/harness.py --lines 1:40")

# Create or overwrite a file via stdin
act(cmd="edit write notes/summary.md", stdin="# Summary\n\n- Point 1\n")

# Replace lines start:end (1-indexed, inclusive) with stdin content
act(cmd="edit replace notes/summary.md --lines 3:3", stdin="- Updated Point 1")
```

## `web` — Search and Markdown Reader

Zero-config web search via DuckDuckGo Lite (or automatic override via `SEARXNG_URL`, `BRAVE_API_KEY`, or `TAVILY_API_KEY` environment variables), plus clean HTML-to-Markdown extraction:

```text
act(cmd='web search "SQLite WAL concurrency" --max 5')
act(cmd="web fetch https://www.sqlite.org/wal.html")
```

## `mem` — Pinned Scratchpad & BM25 Observation Recall

When raw tool outputs age past $K=2$ turns, Tether folds them into 1-line tombstones (`[obs_3 folded: ...]`). The `mem` tool lets the agent pin key facts into active context or search/recall folded observations from SQLite FTS5:

```text
# Pin a key-value fact into active working memory
act(cmd="mem pin db_engine sqlite_wal")

# Search across all folded observations in the session using BM25 ranking
act(cmd='mem search "checkpoint starvation" --top 3')

# Recall a specific observation in full by ID
act(cmd="mem recall obs_3")
```
