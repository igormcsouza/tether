# Everyday work ladder: Claude Haiku

*For: people who want to know how tether does outside coding: writing, answering questions from documents, reviewing ideas and pulling data out of text. After reading you know what the four everyday kinds of the [ladder](index.md) ask, how Claude Haiku did on them through tether, and how to run them on your own model.*

## What was run

The 15 everyday tasks (`content`, `qa`, `critique`, `extract`, described on the [ladder page](index.md#everyday-work-content-qa-critique-extraction)) and the 24 coding tasks, each once (`--single`), on Claude Haiku through tether with a Claude CLI command provider declared in `providers.yaml`, context 32,768, tools `edit,bash`. One shard per kind, all eight in parallel:

```bash
uv run python bench/ladder/run.py --out /tmp/ladder-general/qa --models haiku --ctx haiku=32768 \
    --provider my-claude --kinds qa --single --wall 600 --tether-bin .venv/bin/tether
uv run python bench/ladder/report.py /tmp/ladder-general/qa
```

A run stops as soon as its deliverable passes the grader, so steps and tokens are what it took to deliver.

## Results

| Kind | Passed | Mean score | Prompt tokens | Steps | Time |
|---|---|---|---|---|---|
| content | 4 of 4 | 1.00 | 14,266 | 10 | 84 s |
| qa | 4 of 4 | 1.00 | 21,842 | 13 | 80 s |
| critique | 4 of 4 | 1.00 | 16,092 | 11 | 86 s |
| extract | 3 of 3 | 1.00 | 15,955 | 10 | 60 s |
| **everyday, total** | **15 of 15** | **1.00** | **68,155** | **44** | **310 s** |
| write | 5 of 6 | 0.97 | 49,500 | 23 | 134 s |
| bugfix | 5 of 6 | 0.94 | 53,791 | 26 | 148 s |
| plan | 5 of 6 | 0.88 | 71,318 | 26 | 186 s |
| review | 6 of 6 | 0.97 | 25,248 | 17 | 124 s |
| **coding, total** | **21 of 24** | **0.94** | **199,857** | **92** | **592 s** |

Tokens, steps and time are sums over the tasks of a kind. The eight shards ran side by side.

## What it says

- **Haiku delivers every everyday task**, in 2 to 4 steps and about 4,500 prompt tokens per task, against about 8,300 per coding task. The deliverables read well: the public post leaves out the internal names and the unreleased pricing, the Q&A says "Not in the documents" instead of guessing and uses the corrected values from the later email, the JSON marks the missing products `null`.
- **The everyday kinds have no headroom for a model this strong.** They were sized for small local models, `qwen3.5:9b` among them; for Haiku they only show that tether does not get in the way when the job is text, not code. A harder tier (longer documents, more distractors) is what it would take to separate frontier models.
- **The three coding misses are the model's, not tether's.** `bugfix-4` and `write-6` are the same two tasks Haiku also misses through Claude Code (see the [Haiku coding results](claude-haiku.md)): an edge case the hidden tests check and the goal leaves unsaid. `plan-5` is a sound plan that names `Cart(...)` and `save_orders` but not the file names `cart.py` and `storage.py` the rubric looks for, and proposes new files (`orders.py`, `test_customers.py`) the grader counts as invented. That is a grader that is stricter than a reader would be, not a harness fault.
- **No friction events** (nudges, stalls, tool errors) were recorded in any of the 39 runs.
