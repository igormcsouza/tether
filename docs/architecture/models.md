# Models we have tested

*For: people choosing a model for tether, and contributors who need to know what each model has been seen doing. After this page you know which models were tested, what each is good and bad at, and how each scored on every task of the Coding Ladder.*

Every model here was run through the [Coding Ladder](../benchmarks/ladder/index.md): 24 tasks on a small shop project, four kinds of work (write, bugfix, plan, review) in six tiers of difficulty. A task passes when every hidden test passes (plans and reviews at 0.7). Scores are fractions of the hidden tests or checklist. One run per cell: **a difference of one or two tasks is noise.**

## Summary

| Model | Where it ran | Ladder (tether) | Polyglot-Python | In one line |
|---|---|---|---|---|
| `qwen3.5:9b` | Ollama, 8 GB GPU | 19 of 24, mean 0.87 | 45 of 68 (66%) | The reference small model: solid on stated tasks, blind to unstated ones |
| `qwen3.5:4b` | Ollama, 8 GB GPU | 13 of 24, mean 0.70 | not run | Reaches the same tiers as the 9B in the climb, weaker per task |
| `qwen2.5-coder:7b` | Ollama, 8 GB GPU | 1 of 24, mean 0.28 | not run | Short single-file changes only |
| Claude Haiku | Claude CLI provider | 20 of 24 | 68 of 68 | Saturates the exercises; the ladder separates it from the rest |
| Nemotron 3 Ultra | NVIDIA free tier | 19 of 24, mean 0.92 (bare loop: 16) | not run | Strong and free, but slow per step and rate-limited |
| MiniMax M3.1 Flash | NVIDIA free tier | 6 of 24 (bare loop: 6) | not run | Weak and slow; tether made no difference |

The Haiku and hosted-model rows come from single runs on earlier builds of tether (v0.2.14 and v0.2.10); the local-model rows are the committed baseline (v0.2.18).

## What each one does well and badly

### `qwen3.5:9b` (the reference)

- **Does well.** Tiers 1 to 3 of write and bugfix; plans of every tier, including multi-module ones; reviews that find the obvious planted bugs (an off-by-one, a SQL injection, a mutable default argument). Recovers from its own typos when the error message says what to do. Fixes a failing test and passes it; with `--verify` that is reliable.
- **Does badly.** Cases nobody stated (page 0, empty input, the second bug in a two-bug repair): tier 4 is a wall for every local model. Reviews stop where three bugs are planted and one is quiet, such as a file never closed. It picks a design early and rarely revises it: in 50 failing Polyglot runs, 35 were a misread specification, and the repairs were whole-file rewrites (354 rewrites, no targeted edit). It sometimes thinks until its window is full. A 100-line rewrite costs 30 to 100 seconds.
- **Settings that help.** Large window that stays on the GPU (32,768 on 8 GB); `--verify` with your own tests; the edge cases written into the goal; thinking on for plans and multi-step fixes.

### `qwen3.5:4b`

- **Does well.** The same tiers as the 9B in the climb (write 3, bugfix 3, plan 6, review 2), so on this ladder the size is not what stops tier 4.
- **Does badly.** Per task it is weaker: it fails plan-3 and plan-5 that the 9B passes, and an arithmetic-rounding bugfix (bugfix-5). On the 4B a bare tool loop scored three tasks higher than tether (16 against 13); that is at the edge of the noise and we treat it as an [open question](decisions.md#open-questions), not a verdict.

### `qwen2.5-coder:7b`

- **Does well.** The simplest write and plan tasks, and little else.
- **Does badly.** No thinking mode. It often writes whole files without reading them, and it writes tool calls in forms a harness does not expect (`edit(file=..., content=...)`, JSON as text, `done --stdin`). Tether translates those into real commands; without that translation it scored 0 of 24. Give it the file and the place, and use `--verify`.

### Claude Haiku

- **Does well.** Everything on Polyglot-Python (68 of 68, 3.6 steps per run), including the 11 exercises `qwen3.5:9b` never passes; reviews of every tier. With tether: 20 of 24 on the ladder, against 18 for plain Claude Code on the same tasks.
- **Does badly.** Fails bugfix-4 (the report adding January 2025 and 2026 together) and the largest write task (write-6, 0.83). Its main difference from the small models is cost, not skill: with tether the 24 tasks used 456,863 tokens, against 3,982,119 for plain Claude Code.

### Nemotron 3 Ultra (free tier)

- **Does well.** Scoped tasks of about 15 lines in one file, the review, writing a short script, and checked work: with tether it passed 19 of 24 against 16 for a bare loop, so the harness helps a strong model too.
- **Does badly.** Slow per step on the free tier (rate limit of 40 requests a minute, and 429 answers when several sessions run at once). Given a two-file task or an unscoped goal in a large repository it read for 25 steps without writing. Rewriting documentation it invented API facts, so docs need a fact-check. Use scoped briefs and a pinned check.

### MiniMax M3.1 Flash

- **Does well.** Little observed.
- **Does badly.** 6 of 24 with and without tether, some runs killed by the wall clock, 195 minutes for the 24 tasks. It is the one model where the harness made no difference.

## Every task, every model

First-attempt scores of the ladder tasks for the local models (tether v0.2.18) and for Claude Haiku (tether v0.2.14). A bare number is a pass, `fail` a score below the pass mark, `-` a task that was not reached because a lower tier ended the climb for that kind.

| Task | What it asks | qwen3.5:9b | qwen3.5:4b | qwen2.5-coder:7b | Haiku |
|---|---|---|---|---|---|
| write-1 | Add given lines at the end of a file | 1.00 | 1.00 | 0.00 fail | 1.00 |
| write-2 | Add `slugify(text)` to a utils module | 1.00 | 1.00 | 0.75 fail | 1.00 |
| write-3 | Coupon codes at checkout, file not named | 1.00 | 1.00 | 0.20 fail | 1.00 |
| write-4 | Pagination for the inventory list (edge cases unsaid) | 0.67 fail | 0.67 fail | 0.17 fail | 1.00 |
| write-5 | Sales tax by region across several modules | 1.00 | 0.50 fail | 0.00 fail | 1.00 |
| write-6 | An `export` command for the shop CLI | 0.83 fail | 0.83 fail | 0.33 fail | 0.83 fail |
| bugfix-1 | A `>` that must be `>=` | 1.00 | 1.00 | 0.67 fail | 1.00 |
| bugfix-2 | Adding the same item twice overwrites the quantity | 1.00 | 1.00 | 0.00 fail | 1.00 |
| bugfix-3 | Stock changed after a refused sale | 1.00 | 1.00 | 0.67 fail | 1.00 |
| bugfix-4 | Monthly report mixes two Januaries (two bugs, one reported) | 0.67 fail | 0.67 fail | 0.33 fail | 0.67 fail |
| bugfix-5 | Revenue a few cents low (rounding) | 1.00 | 0.00 fail | 0.00 fail | - |
| bugfix-6 | Tests pass alone, fail together (shared state) | 1.00 | 1.00 | 0.00 fail | - |
| plan-1 | Plan `Cart.remove(sku)` | 1.00 | 0.80 | 0.80 | 1.00 |
| plan-2 | Plan a low-stock alert | 1.00 | 1.00 | 0.40 fail | 1.00 |
| plan-3 | Plan order history and storage | 0.86 | 0.00 fail | 0.57 fail | 0.90 |
| plan-4 | Plan multi-currency, decide what is left open | 0.90 | 0.50 fail | 0.25 fail | 1.00 |
| plan-5 | Plan customer accounts with discounts | 0.90 | 0.00 fail | 0.33 fail | 0.90 |
| plan-6 | Plan turning the CLI into subcommands | 0.70 | 0.89 | 0.44 fail | 0.80 |
| review-1 | Review one function against its docstring | 1.00 | 1.00 | 0.00 fail | 1.00 |
| review-2 | Review a module against its docstrings | 0.85 | 0.85 | 0.00 fail | 1.00 |
| review-3 | Review code that takes user input (three planted bugs) | 0.67 fail | 0.67 fail | 0.67 fail | 1.00 |
| review-4 | Review a module and its caller, only real problems | 0.33 fail | 0.00 fail | 0.00 fail | 1.00 |
| review-5 | Review a pull-request diff | 0.75 | 0.75 | 0.00 fail | 1.00 |
| review-6 | Review four new modules on a branch | 0.83 | 0.67 fail | 0.17 fail | 0.83 |

**Totals (tasks passed of 24):** qwen3.5:9b 19, qwen3.5:4b 13, qwen2.5-coder:7b 1; Claude Haiku passed 20 through the climb (two attempts per tier). The Haiku column is from the tier grids in the [Haiku results](../benchmarks/ladder/claude-haiku.md): some cells (`bugfix-5`, `bugfix-6`) were never reached.

## How to read it

- **The pattern matters more than the totals.** Every model falls off at the same kinds of tasks: unsaid cases (write-4, bugfix-4), long-range review (review-3, review-4), and multi-module changes (write-6). Write those cases into the goal and the same model often passes.
- **Plans are the easy kind.** In the climb (several attempts per tier) both qwen3.5 models reach plan tier 6; the 7B coder is the exception because it does not plan well without a thinking mode. First attempts are less reliable, as the 4B column shows.
- **Use the table to pick a floor.** If your task looks like a task a model fails above, give it a smaller piece, or a bigger model, or a check command.

To add a model, run the ladder on it ([how](../benchmarks/ladder/index.md#run-it)) and add its column here with a short does-well / does-badly note.
