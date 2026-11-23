# Benchmarks

*For: people comparing tether with other tools, and anyone who wants to check that a release did not make small models worse. After this page you know which benchmarks tether uses, what each answers, and where to find the numbers.*

Tether makes one promise: **a small model with tether finishes more real work than the same model without it.** The benchmarks exist to check that promise on every release, honestly, including when the answer is "no change".

| Benchmark | The question it answers | Size | Page |
|---|---|---|---|
| **Polyglot-Python** | How many real coding exercises does a small model finish? | 34 exercises, 2 runs each | [Polyglot-Python](polyglot.md) |
| **Coding Ladder** | How far up a ladder of tasks does a model climb, and what stops it? | 24 tasks (6 tiers x 4 kinds), plus 15 everyday tasks | [The Coding Ladder](ladder/index.md) |

## The short version

- **Polyglot-Python**, `qwen3.5:9b`: 51.5% (35 of 68) at the first measurement to **66.2% (45 of 68)** at v0.2.18, with the same 9B model. A bare tool loop on the same model finishes 12.5% on the fast set. Details and every version: [Polyglot-Python](polyglot.md).
- **Coding Ladder**: the same 9B model through tether passes 19 of 24 tasks, a bare loop 15, a full-featured agent (opencode) 13. Claude Haiku passes 20 of 24 through tether and 18 through plain Claude Code, using about nine times fewer tokens. See [results](ladder/results.md) and [the Haiku comparison](ladder/claude-haiku.md).
- **Models:** what each tested model does well and badly, task by task, is on [Models we have tested](../architecture/models.md).

## Why two benchmarks

Polyglot has one number and thousands of runs behind it, which makes it good for tracking a trend and bad at telling you *why*. For a strong model it is full (Claude Haiku passes all 68), so it cannot separate harnesses. The ladder is the opposite: it shows where each model stops and which kind of task stops it, and it runs in minutes. Use Polyglot to decide whether a change helped. Use the ladder to decide whether a model, or a harness, is right for your work.

## How we keep the numbers honest

- **Paired comparisons.** Two builds run the same exercises with the same settings, and the score delta comes with a confidence interval and the count of runs that flipped each way. Two bare totals side by side are not a comparison.
- **Noise is stated.** One run is noisy by about 0.1 of score; 24 runs differ by two or three passes between identical builds. A gain inside that is reported as flat.
- **Failures are broken down.** Provider outages and timeouts are kept apart from the harness's own outcomes (out of steps, stuck, wrong answer) so you can see which one moved.
- **A change that did not help stays in the record.** The history of every full run is committed in `bench/history.jsonl`, and ideas that did not work are listed with their evidence in [Not adopted](../architecture/decisions.md#not-adopted-and-why).
- **Decide fast, then confirm.** Offline replay of recorded sessions and fixed-seed repeats come first; a full overnight run only confirms.

## Run them

Both live in `bench/` of the repository, not in the package and not in CI, because they need real models. Each page has the commands. Start with the fast set:

```sh
uv run python bench/run.py --runners tether --models ollama/qwen3.5:9b --tasks polyglot-fast --trials 2 --out /tmp/bench
python3 bench/report.py /tmp/bench
```
