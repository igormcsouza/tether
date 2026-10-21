# Context and SQLite Store

## `tether.context`

::: tether.context
    options:
      show_root_heading: false
      members_order: source

## `tether.store`

::: tether.store
    options:
      show_root_heading: false
      members_order: source

## Structured history replay

When the provider sets `structured_history = True` (Ollama, OpenAI-compatible, Anthropic), `ContextAssembler(structured=True)` replays each past action as an assistant `tool_calls` message (`act` with `cmd` and a bounded `stdin`) followed by a `tool` message holding the (folded) observation, instead of `act('...')` text and `Observation:` user text that small models imitated into real arguments ([#38](https://github.com/igormcsouza/tether/issues/38)). `stdin` is replayed as a real prefix (400 chars, then `…`), never a `<N chars>` placeholder that could be copied literally. A call and its result are one unit when trimming to `max_context_tokens`; an action with no result yet, and tool turns with no preceding action (pipeline digests), fall back to the textual form. The system prompt and tools array are unchanged (Rule 1).

## Observation folding and small models

Raw tool outputs stay in the prompt for $K=2$ turns, then fold into a one-line tombstone (see [Built-in Tools](../tutorial/built-in-tools.md#mem-pinned-scratchpad-bm25-observation-recall)). For small models this has consequences ([#27](https://github.com/igormcsouza/tether/issues/27)), seen in the [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course):

- **Fix (#69).** Folding exception: the latest read of each of the last 8 files (`edit view <p>`, `bash cat/head/tail/sed -n <p>`; paths normalized against the workspace) is not folded until `<p>` is edited (`edit write|replace`, or any other bash command naming it: `sed -i`, `tee`, redirects, `python -c`) or re-read. The 2,400-char head+tail elision still applies, and the hard context budget remains #81. The `mem recall` hint is shown only when `mem` is enabled (else "re-run the command"). (`ContextAssembler(mem_enabled=..., workspace_root=...)`, `MAX_LIVE_READS`).
- **Re-viewing files loops, then invents data.** The model runs `edit view`, the output folds two turns later, it views again, and eventually writes from memory.
- **What worked: one compact joined view, used right before the write, that ends with the exact next call.** The `course-source <module>` tool returns a module's plan and chosen videos in one output and finishes with `NOW WRITE THIS MODULE: act("edit write part-N.md", ...)`, so the data is still in the prompt when the write happens.
- **Write long outputs in small pieces.** One big write dropped a whole section. The writer skill writes one `part-N.md` per module with `edit write`, then a `course-build` tool concatenates them into `course.md`.
