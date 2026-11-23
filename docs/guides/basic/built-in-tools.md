# Built-in Tools

*For: anyone choosing what a session may do. After this page you can enable exactly the tools a task needs and nothing more.*

By default, Tether loads **only** the `done` command so pure reasoning tasks pay zero tool-schema overhead. You can enable any combination of built-in tools via `--tools` (CLI), `Harness(tools=[...])` (SDK), or `tools: [...]` (Skill frontmatter).

| Namespace | Summary Line (`<= 12 tokens`) | Purpose |
|---|---|---|
| `done` | `done : Finish task and submit final deliverable` | Mandatory explicit termination command |
| `bash` | `bash : Execute sandboxed shell command in workspace` | Kernel-sandboxed (`bwrap`), env-scrubbed shell execution |
| `edit` | `edit : View, write, or replace lines in workspace files` | Workspace-jailed file viewing and `stdin` patching |
| `web` | `web : Search the web or fetch URL as markdown` | Zero-config DuckDuckGo Lite search & HTML-to-Markdown reader (`fetch` blocks private addresses) |
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
act(cmd="bash grep -n \"return list\" app/main.py | head")
act(cmd="bash", stdin="python3 - << 'EOF'\nimport math\nprint(math.pi)\nEOF")
```

A test run piped to `head` (`python3 -m unittest 2>&1 | head -50`) still shows how it ended: tether keeps the first lines, marks what it cut, and adds the last lines with the summary and the tests' own exit code.

A command that times out after starting a background job (`server &`) gets one more line saying so, with the two fixes: run it in the foreground with `timeout N <cmd>`, or send its output away with `<cmd> >/dev/null 2>&1 &`.

## `edit` — Workspace-Jailed File Operations

Provides deterministic line-numbered viewing and `stdin`-based writing/replacement without sed/awk quoting bugs:

```text
# View a file or a specific line range
act(cmd="edit view tether/harness.py --lines 1:40")

# Create or overwrite a file via stdin
act(cmd="edit write notes/summary.md", stdin="# Summary\n\n- Point 1\n")

# A one-line file can take its text after the path (no stdin)
act(cmd="edit write VERSION 1.4.0")

# Replace lines start:end (1-indexed, inclusive) with stdin content
act(cmd="edit replace notes/summary.md --lines 3:3", stdin="- Updated Point 1")
```

## `web` — Search and Markdown Reader

Zero-config web search via DuckDuckGo Lite (or automatic override via `SEARXNG_URL`, `BRAVE_API_KEY`, or `TAVILY_API_KEY` environment variables), plus clean HTML-to-Markdown extraction:

```text
act(cmd='web search "SQLite WAL concurrency" --max 5')
act(cmd="web fetch https://www.sqlite.org/wal.html")
act(cmd="web fetch https://docs.python.org/3/library/stdtypes.html#str.splitlines")
act(cmd="web fetch https://www.sqlite.org/wal.html --from 'checkpoint'")
```

`#anchor` starts the text at that element, `--from <text>` at the first match; a cut page prints the `--from` words to continue with.

## `mem` — Pinned Scratchpad & BM25 Observation Recall

When raw tool outputs age past $K=2$ turns and the history fills more than half of the context budget, Tether folds them into 1-line tombstones (`[obs_3 folded: ...]`). The `mem` tool lets the agent pin key facts into active context or search/recall folded observations from SQLite FTS5:

```text
# Pin a key-value fact into active working memory
act(cmd="mem pin db_engine sqlite_wal")

# Pin a workspace-wide fact visible to every session, and search across all sessions
act(cmd="mem pin --project test_cmd pytest")
act(cmd="mem search --project test")

# Search across all folded observations in the session using BM25 ranking
act(cmd='mem search "checkpoint starvation" --top 3')

# Recall a specific observation in full by ID
act(cmd="mem recall obs_3")
```

---

## Example: course builder

The [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course) uses `edit` and custom tools to turn a plan into a course. Three limits shaped it:

- **`edit write` replaces the whole file.** Overwriting an existing file now reports `Replaced N lines with M (X removed, Y added; first removed: ...)` and, when the file shrank, points to `edit replace --lines a:b` ([#40](https://github.com/igormcsouza/tether/issues/40)). Small models assume it appends and silently lose earlier content. To build a file in parts, use `edit append <path>` with the next part in `stdin`; it creates the file if needed and adds a newline when the file does not end with one. To add lines in the middle, use `edit insert <path> --line N` with the lines in `stdin`: they go before line N and nothing is replaced (N = lines + 1 appends).
- **`web search` cannot reliably find a specific YouTube video.** Use a [custom tool](../advanced/sdk-and-custom-tools.md#pattern-numbered-candidates) that returns numbered candidates instead.
- **Tools are opt-in.** The searcher skill lists `tools: [yt-todo, yt-candidates, yt-save]` and nothing else; `edit` is only loaded by the stages that write files.

Re-viewing files with `edit view` also interacts badly with observation folding; see [Context and SQLite Store](../../reference/context-and-store.md#observation-folding-and-small-models).

## Turn tools on

Nothing but `done` is on until you ask. Name what the job needs:

```bash
tether run --tools bash,edit "Create hello.py that prints hello and run it"
tether run --tools web "What changed in Python 3.14?"
tether run --tools all "..."          # every built-in, for a quick experiment only
```

A tool you did not enable answers with what is on, so the model can correct itself. This is real output from a session that had `bash` and `edit` and tried a bare `python`:

```text
Error: unknown command `python`. Enabled tools: done, bash, edit.
```

## Why it works this way

- **Everything is off until you turn it on.** Each enabled tool adds a line to the prompt on every step, and each is a way to break something. `done` alone is enough for a question; add `web` for research, `bash,edit` for code ([one action for everything](../../concepts/one-action-primitive.md)).
- **`edit` exists next to `bash`.** Shell redirection is easy for a model to get wrong (quotes, newlines, a lost heredoc). `edit` takes the content in `stdin`, refuses to wipe a file silently, and says how many lines it replaced or removed.
- **Long output is kept, not shown.** `web fetch` and `bash` store everything in SQLite and show the model a head and tail, so a long page never fills its memory ([context and folding](../../concepts/context-and-folding.md)).

## When it goes wrong

- **`Error: bash is disabled`.** The message lists the tools that are on; add one with `--tools bash,edit`.
- **A write replaced a whole file.** `edit write` overwrites; use `edit append` to add, or `edit replace` for a range.
- **`web search` returns nothing useful.** Some search engines refuse automated clients; tether says so, and you can set `SEARXNG_URL`, `BRAVE_API_KEY` or `TAVILY_API_KEY`.

See also [Troubleshooting](../../troubleshooting.md).
