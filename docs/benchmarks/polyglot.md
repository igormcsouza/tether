# Polyglot-Python

*For: people comparing tether with other harnesses, and anyone checking that a release did not make small models worse. After this page you know what the benchmark measures, how tether's score changed from version to version, what we learned, and how it compares with a bare model and with other harnesses.*

Polyglot-Python is the number tether is judged by: **how many real coding exercises a small local model finishes when tether is the harness around it.** Every change either improves it or is not allowed to lower it. The target is 74% (50 of 68 runs) on `qwen3.5:9b` by v0.4.0.

## What is measured

The 34 Python exercises of Aider's [polyglot benchmark](https://github.com/Aider-AI/polyglot-benchmark): poker hands, a Forth interpreter, a REST API, a reactive spreadsheet, a bowling scorer and so on. For each, the model gets a workspace with a stub and the exercise's own test file, and a goal: make the tests pass.

- **Graded by the exercise's own tests.** The test file is restored before grading, so editing it cannot pass.
- **Score** is the fraction of tests that pass, so a partial solution counts. A **pass** is every test green.
- **The full set** is all 34 exercises twice (68 runs), about five hours on one 8 GB GPU. The **fast set** is 12 mixed exercises twice (24 runs), about an hour and a half.
- Each run has a 600-second wall-clock cap, so slow runs end as a failure of time, not of skill.

## How the score changed, version by version

`qwen3.5:9b` through Ollama, default configuration, 34 exercises x 2 runs.

| Version | Passes | Mean score | Steps per run | Prompt tokens per run | What came with it |
|---|---|---|---|---|---|
| baseline (v0.2.9 + fixes) | 35 of 68 (51.5%) | 0.718 | 18.2 | 82,000 | The first full measurement; 14 exercises never pass |
| v0.2.10 | 35 of 68 (51.5%) | 0.763 | 17.9 | 77,700 | Outage retries, thinking headroom, compact output, test index |
| v0.2.13 | 37 of 68 (54.4%) | 0.783 | 17.9 | 77,200 | A wrap-up turn after a change, loop warnings that say to write the file |
| v0.2.15 | 40 of 68 (58.8%) | 0.756 | 17.6 | 75,400 | Thinking capped per turn, a cut call asked again without thinking |
| v0.2.18 | **45 of 68 (66.2%)** | **0.830** | **11.4** | **64,500** | The repair loop around tests, and the 32k default context |

Until v0.2.15 the window was 8,192 tokens. v0.2.18 is the first run at the 32,768 default, so its gain belongs to the larger window and to the harness changes together.

**What clears the noise.** One run of one exercise is noisy (about 0.1 of score), and 24 runs have a spread of two or three passes. Only v0.2.18's gain clears it: the paired score delta against v0.2.15 is +0.074 with a 95% interval of +0.003 to +0.147, and 7 runs flipped to a pass against 2 flipping the other way. The earlier steps (v0.2.10 to v0.2.15) are inside the noise: for v0.2.15 the paired score delta is -0.026 (interval -0.093 to +0.041), 7 flips up and 4 down.

## What we learned

- **A fixed cap on tool output made models re-read.** Cutting every observation at 2,400 characters cut a 6 to 12 KB test file to head and tail and the model read it again and again. Raising the cap to a third of the window moved the mean score from 0.64 to 0.80 on the fast set. ([context and folding](../concepts/context-and-folding.md))
- **Runaway thinking was the biggest hidden loss.** 53 turns in 68 runs ended with no command because the model thought until the window was full, and in runs that hit the time cap 41% of the model's time went to those turns. Bounding thinking removed most of them. ([thinking and sampling](../concepts/thinking-and-sampling.md))
- **The first design is the real failure.** Of 50 failing runs, 35 misread the specification and never revised the plan; repairs were whole-file rewrites. Wording changes to nudges did nothing (about fifteen were tried). ([the repair loop](../concepts/repair-loop.md))
- **Most failures are time, not steps.** In v0.2.18, 17 of the 23 failures hit the wall cap and 6 were handed back stuck. The runs are shorter in steps (11.4 against 17.6) but longer in time (302 s against 260 s), because the larger window and the test re-runs cost seconds.
- **The same 7 exercises never pass:** bowling, forth, react, rest-api, scale-generator, sgf-parsing, transpose. They are not planned for. 27 of the 34 have passed at least once, and 20 passed in both trials in the latest run, so the work is reliability.

## Compared with a bare model and with other harnesses

| Setup | Result | Same set? |
|---|---|---|
| **tether**, `qwen3.5:9b` | 12 of 24 on the fast set (baseline), 45 of 68 on the full set (v0.2.18) | |
| **A bare tool loop**, the same model (a few lines that give it a shell and a file tool) | 3 of 24 on the fast set (12.5%), mean score 0.243 | same fast set, same model |
| **little-coder**, a harness built for small models | 52.9% on the same 34 exercises in its own report | its own setup, not re-run by us |
| **tether**, Claude Haiku | 68 of 68, 3.6 steps per run | same set; saturated, so it cannot separate harnesses |

Read this as three statements. A small model with no harness is a long way behind: the same weights go from 12.5% to 50% on the fast set once tether is around them. Tether's 66% on the full set is ahead of the 52.9% the best published small-model harness reports, though the setups differ and the figures are not directly comparable. And for a strong model the set is full, so the [Coding Ladder](ladder/index.md) is the benchmark that compares harnesses on Claude Haiku, `qwen3.5` models and others.

## Run it yourself

The benchmark lives in `bench/` of the repository (not in the package, not in CI). It needs the exercises cloned once and a model:

```sh
# fast set, two trials, one local model
uv run python bench/run.py --runners tether --models ollama/qwen3.5:9b \
    --tasks polyglot-fast --trials 2 --poly-verify --out /tmp/bench

python3 bench/report.py /tmp/bench       # pass rate, mean score, failure breakdown
```

- `--tasks polyglot` runs all 34 exercises.
- `--tether-bin /path/to/venv/bin/tether` compares two versions on the same machine.
- `--runners tether,naive` adds the bare tool loop, to separate the harness from the model.
- `--redo-infra` reruns cells that failed on a provider outage.
- `bench/compare.py` gives the paired score delta and flips between two runs. Use it, not two numbers side by side.

## How to compare fairly

- Same model, same server, same context, same machine, run in the same session (a busy GPU changes time limits).
- Report the pass count and the mean score, with the failure breakdown. The breakdown keeps outages apart from the harness outcomes (`max_steps`, `stalled`, `wrong_answer`, `worker_error`).
- A difference smaller than the noise is not a result. Do not draw a conclusion from one trial of one exercise.
- Decide with a fast check (replay recorded sessions, a fixed-seed repeat) before spending hours of GPU time.

More: [`bench/README.md`](https://github.com/igormcsouza/tether/blob/main/bench/README.md), and the full history in `bench/history.jsonl`.
