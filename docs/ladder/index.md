# The Coding Ladder

*For: people choosing a local model for coding work, and anyone who wants to check what tether does to a model before trusting it. After reading you can run the ladder on your own model and read its result.*

The **Coding Ladder** is tether's own benchmark. It answers one question: **how far up a ladder of coding tasks does this model climb when tether is the harness around it, and what stops it?** The [results](results.md) page holds the baseline for the models tested so far.

## The shape

There are 24 tasks: **6 tiers of difficulty × 4 kinds of work**. All of them are on the same small `shop` project, so a model's score differs by what it is asked, not by what it has to learn first.

| Tier | What the task gives the model |
|---|---|
| 1 | The file, the place and the exact code to add |
| 2 | The behaviour to implement, in one function |
| 3 | The behaviour only: the model finds the right file itself |
| 4 | A goal with cases left unsaid (input validation, empty input) that a careful engineer would still handle |
| 5 | A change that spans several modules and must keep the existing tests green |
| 6 | An open goal in a bigger codebase |

| Kind | What the model delivers | How it is graded |
|---|---|---|
| **write** | New code for a feature | Hidden unit tests, the fraction that pass |
| **bugfix** | A repair, starting from a symptom | Hidden unit tests, the fraction that pass |
| **plan** | A `plan.md` for a feature | A checklist of things a good plan names (files, edge cases, order of work); invented files cost points |
| **review** | A `review.md` of code with planted bugs | Share of the planted bugs found; false alarms cost points |

Code is graded by tests the model never sees. A task passes when every hidden test passes (plans and reviews pass at 0.7). `python3 bench/ladder/validate.py` proves each grader: the starting state fails and a reference solution passes.

## How a model climbs

For each model and each kind the tiers are tried in order. A tier gets **up to four attempts**, and the first pass moves the model up:

1. thinking off, default settings;
2. thinking on;
3. thinking on, more steps and later folding of old tool output;
4. thinking off, temperature 0, more steps and later folding.

If all four fail, that kind's ladder ends and the next tier is never shown. A model without a thinking mode skips the thinking parameter, so its attempts differ only in steps and temperature. A run is stopped as soon as the work passes its grader ("delivered"), so a model that finishes but never calls `done` does not burn time.

The context window is the largest that stays entirely in GPU memory (`bench/ladder/probe.py` finds it), because a window that spills to system memory makes every step much slower.

## Run it

```bash
uv run python bench/ladder/validate.py          # prove the graders (no model needed)

uv run python bench/ladder/run.py --out /tmp/ladder \
    --models qwen3.5:9b --ctx qwen3.5:9b=40960 --tether-bin .venv/bin/tether
uv run python bench/ladder/report.py /tmp/ladder
```

`report.py` prints, per task: whether it passed, how many attempts it took, the best score, the time, the steps and the prompt tokens. Runs are resumable.

## Compare harnesses

The same 24 tasks, each once, on the same model, through a different harness:

```bash
uv run python bench/ladder/run.py --harness naive --single --out /tmp/naive \
    --models qwen3.5-9b-40k --ctx qwen3.5-9b-40k=40960
```

`--harness` takes `tether`, `naive` (a bare tool loop with no harness around the model), `opencode` and `claude` (Claude Code in print mode, with a cost cap). Model copies such as `qwen3.5-9b-40k` carry the context size, because an OpenAI-style endpoint cannot set it.

## Freeze a baseline

`bench/ladder/snapshot.py` copies the results into `bench/ladder/baseline/` and `bench/ladder/charts.py` redraws the charts on the [results](results.md) page from that data. The baseline is committed, so a change to tether can be compared with it.
