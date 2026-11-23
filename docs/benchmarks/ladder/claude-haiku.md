# Coding Ladder results: Claude Haiku with and without tether

*For: people deciding whether tether is worth putting around a model, whether a frontier model like Claude Haiku needs it, and what it costs in time and tokens. After reading you know how far Claude Haiku climbs the [Coding Ladder](index.md) with and without tether, next to `qwen3.5:9b`, where each setup stops, and how the numbers were produced.*

## What was run

Three setups, the same 24 tasks, the same hidden-test and rubric graders, and two attempts per tier:

- **tether + Haiku**: tether v0.2.14 (the released package) with Claude Haiku through a Claude CLI command provider declared in `providers.yaml`. The provider is a `command` entry, so tether starts the Claude CLI for each model call. Context is set to 32,000 for this provider.
- **plain Haiku**: Claude Code in print mode, given the same task text, inside a sandbox that makes everything except its workspace and its login directory read-only. Claude Code manages its own context.
- **tether + qwen3.5:9b**: tether v0.2.14 with `qwen3.5:9b` through Ollama at the default 8,192 context, on one 8 GB GPU.

Each tier gets two attempts. The second attempt gets a one-line hint of how the first ended: the hidden-test count or rubric items, and the end state. The hint never shows the tests themselves.

## How far each climbs

| Setup | write | bugfix | plan | review | Passed |
|---|---|---|---|---|---|
| plain Haiku (Claude Code) | 5 | 3 | 4 | 6 | 18 of 24 |
| tether + Haiku | 5 | 3 | 6 | 6 | 20 of 24 |
| tether + qwen3.5:9b | 3 | 3 | 6 | 2 | 14 of 24 |

The number is the highest tier passed per kind. Totals across the 24 rungs:

- **plain Haiku**: 18 of 24, 632 s, 93 steps, 3,982,119 tokens.
- **tether + Haiku**: 20 of 24, 979 s, 119 steps, 456,863 tokens.
- **tether + qwen3.5:9b**: 14 of 24, 1,159 s, 284 steps, 584,508 tokens.

### Tier grids

In each cell, the score is that of the attempt that decided the tier. `retry` means it passed on the second attempt, `fail` means it failed both, and `-` means a lower tier ended that kind, so the tier was not reached.

**plain Haiku (Claude Code)**

| Tier | write | bugfix | plan | review |
|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | 1.00 | 1.00 | 1.00 | 1.00 |
| 3 | 1.00 | 1.00 | 0.90 | 1.00 |
| 4 | 1.00 | 0.67 fail | 1.00 (retry) | 1.00 |
| 5 | 1.00 | - | 0.60 fail | 1.00 |
| 6 | 0.83 fail | - | - | 1.00 |

**tether + Haiku**

| Tier | write | bugfix | plan | review |
|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | 1.00 | 1.00 | 1.00 | 1.00 |
| 3 | 1.00 | 1.00 | 0.90 | 1.00 |
| 4 | 1.00 | 0.67 fail | 1.00 (retry) | 1.00 |
| 5 | 1.00 | - | 0.90 (retry) | 1.00 |
| 6 | 0.83 fail | - | 0.80 | 0.83 (retry) |

**tether + qwen3.5:9b**

| Tier | write | bugfix | plan | review |
|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | 1.00 | 1.00 | 1.00 | 0.85 |
| 3 | 1.00 | 1.00 | 0.86 | 0.67 fail |
| 4 | 0.67 fail | 0.67 fail | 0.88 | - |
| 5 | - | - | 0.70 | - |
| 6 | - | - | 0.89 | - |

### Per-kind totals

**plain Haiku (Claude Code)**

| Kind | Highest tier | Time (s) | Steps | Tokens | Attempts | Mean score |
|---|---|---|---|---|---|---|
| write | 5 | 154 | 29 | 1,212,559 | 7 | 0.952 |
| bugfix | 3 | 100 | 20 | 848,647 | 5 | 0.867 |
| plan | 4 | 264 | 29 | 1,262,564 | 7 | 0.771 |
| review | 6 | 114 | 15 | 658,349 | 6 | 1.000 |
| **all** | **18 of 24** | 632 | 93 | 3,982,119 | 25 | |

**tether + Haiku**

| Kind | Highest tier | Time (s) | Steps | Tokens | Attempts | Mean score |
|---|---|---|---|---|---|---|
| write | 5 | 268 | 34 | 126,358 | 7 | 0.952 |
| bugfix | 3 | 245 | 31 | 156,128 | 5 | 0.867 |
| plan | 6 | 278 | 34 | 122,760 | 8 | 0.871 |
| review | 6 | 188 | 20 | 51,617 | 7 | 0.905 |
| **all** | **20 of 24** | 979 | 119 | 456,863 | 27 | |

**tether + qwen3.5:9b**

| Kind | Highest tier | Time (s) | Steps | Tokens | Attempts | Mean score |
|---|---|---|---|---|---|---|
| write | 3 | 315 | 69 | 153,556 | 5 | 0.867 |
| bugfix | 3 | 408 | 98 | 248,625 | 5 | 0.867 |
| plan | 6 | 312 | 78 | 141,401 | 6 | 0.887 |
| review | 2 | 124 | 39 | 40,926 | 4 | 0.796 |
| **all** | **14 of 24** | 1159 | 284 | 584,508 | 20 | |

## What stood out

- **tether + Haiku passed 20 of 24 rungs against 18 for plain Haiku.** That two-rung difference is inside the noise of one run per attempt.
- **write and bugfix stop at the same rungs in both Haiku setups, on the same tests.** Write stops at tier 6 at 5 of 6 tests, and bugfix stops at tier 4 at 2 of 3 tests. Those limits belong to the model and the task, not the harness.
- **plan is the only gap that matters: 4 against 6.** Plain Haiku covers every item in the plan checklist, but it names test files that do not exist, and the grader subtracts 0.1 from the score for each. tether + Haiku made the same mistake, and its retry hint fixed it at tiers 4 and 5; plain Haiku's retry fixed it at tier 4 but not at tier 5.
- **review: plain Haiku passed all six tiers on the first try.** tether + Haiku needed one retry, at tier 6.
- **tokens: tether + Haiku processed about 9 times fewer tokens (456,863 against 3,982,119).** Most of plain Haiku's count appears to be Claude Code's own prompt of roughly 30,000 tokens, read from cache on every call (a small test run showed about that much per call). That is a framing cost. It is not a dollar saving, and this page does not claim one.
- **time: plain Haiku was faster (632 s against 979 s).** tether's Claude CLI provider starts the CLI on every model call, which is the likely cause; it was not measured separately.
- **qwen3.5:9b reached tier 6 on plan, like Haiku, but stopped at tier 3 on write and bugfix and at tier 2 on review.** It trails both Haiku setups on write and review and ties them on bugfix.

## Read it with care

- **One run per attempt.** A one-rung difference is noise. Only gaps of several rungs, or a tier that one setup passes and the other never does, say something.
- **Different context handling.** tether + Haiku is configured at 32,000 context. Plain Haiku uses Claude Code's own context management. The two setups are not given the same window.
- **A single machine.** The qwen3.5:9b runs used one 8 GB GPU. Timings on another machine will differ.

## Reproduce it

Replace the placeholders with your own provider name and a logged-in Claude config directory:

```bash
uv run python bench/ladder/run.py --out /tmp/ladder-tether-haiku --models haiku --provider <your-claude-cli-provider> --ctx haiku=32000 --attempts 2 --tether-bin .venv/bin/tether
LADDER_CLAUDE_DIR=<a-logged-in-claude-config-dir> uv run python bench/ladder/run.py --out /tmp/ladder-plain-haiku --models haiku --harness claude --attempts 2
uv run python bench/ladder/run.py --out /tmp/ladder-qwen --models qwen3.5:9b --attempts 2 --tether-bin .venv/bin/tether
```

The Claude CLI provider is the `command` kind of entry described in the [providers reference](../reference/providers.md).
