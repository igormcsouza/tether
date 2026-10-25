# Glossary

*For: anyone meeting a tether term for the first time. Each entry is one sentence you can act on.*

**Act.** The single tool the model sees: `act(cmd, stdin)`. Every command (`bash`, `edit`, `done`, your own) goes through it.

**ACI (agent-computer interface).** The command line the model works with. Tether keeps it small and forgiving: compact usage, helpful errors, normalised quirks.

**Dialect.** A reply format a model uses instead of a proper tool call (for example a `<tool_call>` block). Tether parses known dialects into the same action; add your own with a `dialects:` regex.

**Fold / tombstone.** After a few turns, a tool output is replaced in the prompt by a one-line stand-in (the tombstone). The full text stays in SQLite and can be searched or recalled.

**FTS5 RAG.** Retrieval over SQLite's full-text index (BM25 ranking). `mem search` and `agent query` use it to pull only the relevant chunks, with no embedding model.

**Gate (verification gate).** A command you supply with `--verify` that tether runs itself before accepting `done`. A failing gate sends its output back to the model.

**Headless.** A session run detached in the background (`--headless`). You check it with `tether status`, `wait` and `read`, and steer it with `tether send`.

**Nudge.** A one-line reminder tether adds when the model answers in plain text, or keeps reading after a change, so it acts or calls `done`.

**Pipeline.** An ordered set of stages in YAML; each stage is its own session with its own model, tools and gate.

**Session.** One run of the loop, stored as a row in `.tether/tether.db`. It can be resumed, sent messages and read by another agent.

**Skill.** A Markdown file with YAML frontmatter that packages instructions, model, tools and gates for a repeatable job.

**Stall.** The model repeating a command, cycling, or re-reading one file without changing anything. Tether warns, and ends the session early if it continues.

**Workspace.** The directory a session may read and write. Everything outside it is blocked by the sandbox.
