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
(`REJECT` / `PROMISING` / `FLAT`). A `PROMISING` canary only says "worth a paired A/B" (see *Judging a change* below), not "improved". `--tasks canary` is the same set for `run.py`.

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

## Coding ladder (`bench/ladder/`)

24 coding tasks on a small `shop` project: 6 tiers x {write, bugfix, plan, review}. Tier 1 gives file, place and code; each tier gives less (named behaviour, find the file, edge cases left unsaid, several modules, an open goal). Code tasks are graded by hidden unittest files, plan/review tasks by regex rubrics (reviews lose points for false alarms). `python3 bench/ladder/validate.py` proves every grader (the start state fails, the reference solution passes).

```bash
python3 bench/ladder/run.py --out /tmp/ladder --models qwen3.5:9b,qwen3.5:4b,qwen2.5-coder:7b \
    --ctx qwen3.5:9b=40960,qwen3.5:4b=65536,qwen2.5-coder:7b=32768 --tether-bin .venv/bin/tether
python3 bench/ladder/report.py /tmp/ladder
```

Per (model, kind) the tiers are climbed in order. A tier gets up to 4 attempts, stopping at the first pass: thinking off; thinking on; thinking on with more steps and later folding; thinking off at temperature 0 with more steps. Four failures end that kind's ladder, so the next tier is never tried. A run is stopped as soon as the work passes its grader ("delivered"), so models that never call `done` do not burn GPU time; the report shows steps at delivery. Pick `--ctx` as the largest window that stays fully in VRAM (`/api/ps`: `size == size_vram`).

**Harness comparison.** `run.py --harness tether|naive|opencode|claude --single` runs all 24 tasks once, no stopping, on the same model, so the harnesses can be set side by side (`report.py` prints one block per harness). `naive` is `bench/naive_agent.py` (a bare tool loop), `opencode` runs through the gru `sandbox.sh` and needs an `ollama` provider in `opencode.json` pointing at `http://localhost:11435/v1` plus a model alias created with the same `num_ctx` (`/v1` cannot set it), `claude` is Claude Code in print mode with a $1 budget cap per task.

## Judging a change (what a number can and cannot tell you)

Measured on the baseline and v0.2.10 full runs (#173): 13 of 34 exercises never pass, 11 always pass, and only 10 ever flip. 12 of 68 run slots flipped between the two runs, 6 up and 6 down, and the paired score delta was +0.045 with a 95% CI of [-0.029, +0.121]. A pass rate over 68 runs (standard error ~6 points) and a canary of rows picked *because they failed once* (regression to the mean) both mislead. Use this instead:

1. **Mechanism first (minutes, no GPU).** A change must move its own metric before it earns a run: empty turns, test-file reads, tokens per observation, measured on recorded `t.db` files.
2. **Greedy A/B.** `--param temperature=0` makes a run repeatable: the same code and prompt gave identical command sequences three times, including a run that hit the wall cap. At temperature 0.2 with `--seeded` short runs repeat but runs of 20+ steps drift apart (GPU float order), so seeded sampling only reduces noise. Run the baseline arm once per commit and reuse it; run only the new arm.
3. **Compare, do not eyeball.** `python3 bench/compare.py <before-dir> <after-dir>` pairs runs by exercise and prints the score delta with a bootstrap 95% CI over exercises, the pass flips with an exact sign test, and the mechanism numbers (wall-cap rate, steps, nudges per run). `BETTER`/`WORSE` only when the CI excludes 0; otherwise `NO EVIDENCE`, with the number of runs it would take.
4. **Pick rows before you look**, never by one failure. `--tasks paired` is a fixed 10-exercise set that flips or scores partially (about 40 min per arm).
5. The official number stays the full 34 x 2 run, once per release.

## History (the north-star ledger)

`bench/history.jsonl` is the single source for the tracker's History table (#173). One JSON object per line: `date`, `version`, `model`, `runner`, `tasks`, `trials`, `context`, `runs`, `passed`, `pass_rate`, `mean_score`, failure counts, mean steps/prompt tokens/wall, `note`.

A PR that changes behaviour the model sees appends one line for its own run (same model, default 8192 context, `--poly-verify`) and ends its body with `north star: <before> -> <after> (runs, noise, run dir)`. Noise is about 0.1 per run, so a claim needs enough runs to beat it; a flat result is appended and reported as flat.

The official number is the full 34 exercises × 2 trials (68 runs) with the 600 s per-run wall cap. Use `--tasks polyglot-fast` for quick checks and label it `polyglot-fast-12`.
