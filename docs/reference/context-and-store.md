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

When the provider sets `structured_history = True` (Ollama, OpenAI-compatible, Anthropic), `ContextAssembler(structured=True)` replays each past action as an assistant `tool_calls` message (`act` with `cmd` and a bounded `stdin`) followed by a `tool` message holding the (folded) observation, instead of `act('...')` text and `Observation:` user text that small models imitated into real arguments ([#38](https://github.com/igormcsouza/tether/issues/38)). `stdin` is replayed as a real prefix (400 chars, then `…`), never a `<N chars>` placeholder that could be copied literally. `max_context_tokens` is a hard target: the assembler first folds live observations oldest-first (the newest stays), then drops the oldest call+result groups, then shrinks the newest observation, and scales the target by the `real/estimated` prompt-token ratio the provider reports (1.0 to 1.5). If goal, system prompt and the latest step alone do not fit, it prints one stderr warning (#81). A call and its result are one unit when trimming; an action with no result yet, and tool turns with no preceding action (pipeline digests), fall back to the textual form. The system prompt and tools array are unchanged (Rule 1).

## Observation folding and small models

Raw tool outputs stay in the prompt while there is room. Once the history fills more than half of `max_context_tokens`, an output older than $K=2$ turns folds into a one-line tombstone (see [Built-in Tools](../tutorial/built-in-tools.md#mem-pinned-scratchpad-bm25-observation-recall)). For small models this has consequences ([#27](https://github.com/igormcsouza/tether/issues/27)), seen in the [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course):

- **Fix (#69).** Folding exception: the latest read of each of the last 8 files (`edit view <p>`, `bash cat/head/tail/sed -n <p>`; paths normalized against the workspace) is not folded until `<p>` is edited (`edit write|replace`, or any other bash command naming it: `sed -i`, `tee`, redirects, `python -c`) or re-read. The head+tail elision still applies (an observation may use up to a third of `max_context_tokens`, at least 2,400 chars), and the hard context budget remains #81. The `mem recall` hint is shown only when `mem` is enabled (else "re-run the command"). (`ContextAssembler(mem_enabled=..., workspace_root=...)`, `MAX_LIVE_READS`).
- **Re-viewing files loops, then invents data.** The model runs `edit view`, the output folds (two turns later once the context is more than half full), it views again, and eventually writes from memory.
- **What worked: one compact joined view, used right before the write, that ends with the exact next call.** The `course-source <module>` tool returns a module's plan and chosen videos in one output and finishes with `NOW WRITE THIS MODULE: act("edit write part-N.md", ...)`, so the data is still in the prompt when the write happens.
- **Write long outputs in small pieces.** One big write dropped a whole section. The writer skill writes one `part-N.md` per module with `edit write`, then a `course-build` tool concatenates them into `course.md`.

## Restart after repeated failures, then hand back

For a model that is stuck, the history itself is the problem: the failed commands and their output pull it toward the same step again. Stuck means either of two things: the same check command has failed 3 times with an edit between each run, or the stall guard ended its warnings (repeated command, a cycle of commands, or one file re-read over shifting ranges) and the one `[WRAP UP]` turn did not help. Either way the harness adds one `restart` turn and continues from that turn alone. The message holds the files as they are now (up to 3, capped), the last failing output (trimmed) and short counts of what was tried. Failed commands are not replayed, so the model sees a state to fix rather than a transcript to copy. A session restarts at most twice. If it is stuck again after the second restart, the harness stops spending steps and hands the task back: the session ends `WAITING_INPUT` (exit code `2`) with the same summary, headed `[STUCK ...]`, as its result. The caller, a person or a parent agent, can refine the request and `send` it back. Everything before the restart turn stays in SQLite, and the restart costs no static prompt tokens and no extra model call.

Example of the message (trimmed):

```text
[RESTART at step 14. Earlier steps are not shown; the files are as you left them.]

Your files now:
calc.py:
def add(a, b):
    return a - b

Last result of `pytest -q`:
FAILED test_calc.py::test_add - assert -1 == 5

What was tried so far:
- calc.py changed 3 times
- `pytest -q` run 3 times with a failing result each time
Re-read the failing output above before you change anything.
```

The hand-back has the same body under the header `[STUCK at step 31 after 2 restarts. Handing back to you.]`, and ends with "The work is not progressing. Refine the request or give guidance, then send it again."
