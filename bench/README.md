# bench: model-in-the-loop checks (developers only)

Not part of the `tether` package, not run in CI. Use it to onboard a new model or to check a
release for regressions that deterministic tests cannot see (unit, golden and e2e tests stay the
gate; see `CONTRIBUTING.md`).

Nine tasks in `tasks/<name>/` (workspace in `ws/`, goal in `goal.txt`, hidden tests in `hidden/`):
`focus` (one exact edit in a distractor-heavy repo, scope-checked), `plan` (an implementation plan, checked for named files, failure handling and tests), `codereview` (eight seeded bugs to find, no edits), `code-simple`, `code-medium`, `code-hard` (graded by hidden unit tests; editing the visible tests
scores 0), `qa`, `content`, `review` (graded by constraint counts and keyword checks, so they are
a smoke test for quality, not a judge).

**Polyglot-Python** is the score we answer to. `--tasks polyglot` runs the 34 Python exercises of Aider's
[polyglot-benchmark](https://github.com/Aider-AI/polyglot-benchmark) (cloned once into
`~/.cache/tether-bench/polyglot-benchmark`, or set `POLYGLOT_DIR`); `--tasks polyglot-fast` runs a 12-exercise
subset that mixes passes, partials and failures. Each task is graded by the exercise's own tests (the test file is
restored before grading, so editing it cannot pass), `--poly-verify` adds a `--verify` gate on those tests. Then
`python3 bench/report.py <out>` prints pass rate and mean score with a failure breakdown that keeps provider outages
(`outage`, `timeout`) apart from harness outcomes (`max_steps`, `stalled`, `wrong_answer`, `worker_error`).

**Did my change help? (15 min)** `python3 bench/canary.py /tmp/canary-<change> [--tether-bin <venv>/bin/tether]` runs 7 exercises
once (4 flaky ones that can flip, 3 fast guards) and prints each score next to the pinned baseline with a verdict
(`REJECT` / `PROMISING` / `FLAT`). Only `PROMISING` earns the full 34x2 run. `--tasks canary` is the same set for `run.py`.

Three runners, so a gap can be attributed:

| runner | what it is |
|---|---|
| `tether` | the CLI under test (`--tether-bin` picks a version or a venv) |
| `naive` | `naive_agent.py`, a plain OpenAI-compatible tool loop (bash/read/write) with the same model |
| `claude` | Claude Code in print mode, as a frontier baseline (`--models cc/sonnet`) |

```bash
export NVIDIA_API_KEY=...            # only for nvidia/* models; OLLAMA_HOST defaults to :11435
uv run python bench/run.py --runners tether,naive --models ollama/qwen3.5:9b \
    --tasks code-simple,qa --trials 2 --out /tmp/bench
uv run python bench/run.py --runners tether --tether-bin /path/to/venv/bin/tether \
    --models ollama/qwen3.5:9b --param think=false --out /tmp/bench-v0.2.3
```

Each run lands in `<out>/<runner>__<model>__<task>__t<k>/` with the workspace, stdout, the
session DB (`t.db`) and `done.json`; `results.jsonl` collects them. Re-running skips finished
cells; `--redo-infra` reruns cells that failed on provider errors (429, 503, timeouts).

Read results with the friction events (`syntax_error`, `loop_stall`, `nudge`, ...) next to the
score: a low score with many events is a harness problem, a low score with none is the model.
Rate limits (NVIDIA: 40 requests/min) invalidate results silently; set `rpm:` in `providers.yaml`
and keep parallelism low (`--par nvidia=2`).

Caveats: one run per cell is noisy (about 0.1); the scores are regex and hidden-test based.

## History (the north-star ledger)

`bench/history.jsonl` is the single source for the tracker's History table (#173). One JSON object per line: `date`, `version`, `model`, `runner`, `tasks`, `trials`, `context`, `runs`, `passed`, `pass_rate`, `mean_score`, failure counts, mean steps/prompt tokens/wall, `note`.

A PR that changes behaviour the model sees appends one line for its own run (same model, default 8192 context, `--poly-verify`) and ends its body with `north star: <before> -> <after> (runs, noise, run dir)`. Noise is about 0.1 per run, so a claim needs enough runs to beat it; a flat result is appended and reported as flat.

The official number is the full 34 exercises × 2 trials (68 runs) with the 600 s per-run wall cap. Use `--tasks polyglot-fast` for quick checks and label it `polyglot-fast-12`.
