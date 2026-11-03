# Benchmark Evaluation

*For: people comparing tether with other harnesses, and anyone checking that a release did not make small models worse. It shows what is measured, how, and the latest numbers.*

Tether is judged on one score: **how many real coding exercises a small local model finishes** when tether is the harness around it. That is the number every change has to improve, or at least not lower.

## What is measured

The **Polyglot-Python** set: the 34 Python exercises of Aider's [polyglot benchmark](https://github.com/Aider-AI/polyglot-benchmark) (poker hands, a Forth interpreter, a REST API, a reactive spreadsheet, ...). For each exercise the model gets a workspace with a stub and the exercise's own test file, and a goal: make the tests pass.

- **Graded by the exercise's own tests.** The test file is restored before grading, so editing it cannot pass.
- **Score** is the fraction of tests that pass (so a partial solution counts); a *pass* is every test green.
- The **full set** is all 34 exercises run twice (68 runs), about five hours on one local GPU. The **fast set** is 12 exercises that mix passes, partial results and failures, run twice each (24 runs): about an hour and a half, enough to see a large change.

## Latest result

`qwen3.5:9b` through Ollama (`num_ctx` 8192), all 34 exercises, 2 trials per exercise (68 runs):

| | before v0.2.10 | v0.2.10 |
|---|---|---|
| Passes | 35 of 68 (51.5%) | 35 of 68 (51.5%) |
| Mean score | 0.718 | 0.763 |
| Runs killed by the wall cap | 11 | 14 |

The pass count did not move: the extra score comes from partial solutions, and the runs that still fail mostly lose their time to long empty turns of a few thousand tokens. The [Coding Ladder](ladder/index.md) is the second yardstick: it shows where a model stops climbing instead of one pass rate.

**Read these numbers with care.** One run of one exercise is noisy (about 0.1 of score), 24 runs are a small sample, and a local server can time out for reasons that have nothing to do with tether. A difference smaller than that noise is not a result. The *failure breakdown* in the report keeps provider outages and timeouts apart from harness outcomes (`max_steps`, `stalled`, `wrong_answer`, `worker_error`) so you can see which one moved.

## Run it yourself

The benchmark lives in `bench/` of the repository (not in the package, not in CI). It needs the exercises cloned once and a model to run:

```bash
# fast set, two trials, one local model
uv run python bench/run.py --runners tether --models ollama/qwen3.5:9b \
    --tasks polyglot-fast --trials 2 --out /tmp/bench

# pass rate, mean score and the failure breakdown
python3 bench/report.py /tmp/bench
```

Use `--tasks polyglot` for all 34 exercises, `--tether-bin /path/to/venv/bin/tether` to compare two versions on the same machine, and `--redo-infra` to rerun cells that failed on a provider outage. To attribute a gap to the harness rather than the model, add `--runners tether,naive`: the `naive` runner is a plain tool loop with the same model and the same exercises. Details and the smaller non-coding tasks: [`bench/README.md`](https://github.com/igormcsouza/tether/blob/main/bench/README.md).

## How to compare fairly

- Same model, same server, same `num_ctx`, same machine; run both versions in the same session (a busy GPU changes timeouts).
- Report pass count **and** mean score, with the failure breakdown.
- Do not draw a conclusion from a single trial of a single exercise.
