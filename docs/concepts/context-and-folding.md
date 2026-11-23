# Context and folding

*For: anyone who wants to know what the model actually sees at each step and what happens to the rest. After this page you know when tether folds old output, how a model gets it back, and why we fold only as much as needed.*

## The problem

An agent's work is mostly reading: test output, files, web pages. If every result stays in the prompt, a small model hits the end of its window by step four and forgets the task. If results are thrown away too eagerly, the model reads the same file again and again.

## What the research says

*MemGPT* (Packer et al., 2023) treats the model's window like fast working memory (RAM) backed by slower storage on disk, with the model, or the system around it, moving information between them. The model never needs everything at once; it needs the right piece at the right time, and a way to get the rest.

## What tether does

Everything the model ever saw is stored in full in a local SQLite database (`.tether/tether.db`). What the model sees on each step is a *view* of it, assembled in three tiers.

**1. Keep the head and tail of a huge output.** One output may use up to a third of the window. Past that the middle is cut and replaced by a pointer, keeping the first 60% (the command and headers) and the last 40% (the error and the exit status), which is where the information usually is.

**2. Fold old outputs into one line, but only when needed.** While the history fits in half the window, nothing is folded. Above that, outputs older than two turns fold, oldest first, only until the history is back under the target:

```text
[obs_3 folded: `web fetch https://...` (3,420 chars) | use `mem recall obs_3` to expand]
```

**3. Keep what the model is working on.** The latest read of each of the last eight files stays in full until that file changes or is read again. Re-reading a file that did not change tells the model so ("unchanged") instead of re-running it, and also lengthens the fold window for the rest of the session, up to eight turns.

**Nothing is lost.** The model can ask for any piece back with `mem recall obs_3`, or search everything it has seen with `mem search "database is locked"`. Behind that is SQLite full-text search with BM25 ranking: every output and every final answer is cut into paragraph-sized chunks of about 150 tokens and indexed, so a lookup takes a millisecond and returns only the relevant passages. The same index lets a parent agent ask a sub-agent's work a question without reading its transcript ([multi-agent](../guides/advanced/multi-agent.md)).

## What we learned by measuring

**Too little room made models re-read.** The first version cut every output at 2,400 characters. A test file of 6 to 12 KB was cut to a head and a tail, so models read the same file ten or more times, and 45% of the steps in runs that hit the step limit were reads. Raising the cap to a third of the window moved the mean score of `qwen3.5:9b` from 0.64 to 0.80 and cut re-reads from 32% to 19% of steps. It cost more prompt per step (5.3k to 6.4k tokens) and was worth it.

**Folding too early made models forget.** Folding everything older than two turns, unconditionally, left a model that had read a file with only a one-line tombstone, so it read the file again. Folding only above half the window, only as much as needed, and giving the model longer when it re-reads, keeps the benefit (a short window) without the loop. A paired run of this change showed no loss: pass rate 0.50 to 0.60, steps 16.3 to 12.1, with the confidence intervals overlapping zero.

**Files are worth indexing by their tests.** When a long test file is cut, tether lists its test names (up to thirty), so the model can ask for one test instead of the whole file.

## What it costs

A second place to look: when the model needs old output it has to call `mem recall`, and a model that forgets to will repeat a command. The `[obs_N unchanged]` pointer and the tombstone text exist for exactly that moment.

## References

- Packer, C., et al. (2023). *MemGPT: Towards LLMs as Operating Systems.* [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)
- Decisions: [AD-8 to AD-18](../architecture/decisions.md#b-state-and-sessions). Reference: [context and store](../reference/context-and-store.md).
