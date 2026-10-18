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

## Observation folding and small models

Raw tool outputs stay in the prompt for $K=2$ turns, then fold into a one-line tombstone (see [Built-in Tools](../tutorial/built-in-tools.md#mem-pinned-scratchpad-bm25-observation-recall)). For small models this has consequences ([#27](https://github.com/igormcsouza/tether/issues/27)), seen in the [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course):

- **Re-viewing files loops, then invents data.** The model runs `edit view`, the output folds two turns later, it views again, and eventually writes from memory.
- **What worked: one compact joined view, used right before the write, that ends with the exact next call.** The `course-source <module>` tool returns a module's plan and chosen videos in one output and finishes with `NOW WRITE THIS MODULE: act("edit write part-N.md", ...)`, so the data is still in the prompt when the write happens.
- **Write long outputs in small pieces.** One big write dropped a whole section. The writer skill writes one `part-N.md` per module with `edit write`, then a `course-build` tool concatenates them into `course.md`.
