# bench: model-in-the-loop checks (developers only)

Not part of the `tether` package, not run in CI. Use it to onboard a new model or to check a
release for regressions that deterministic tests cannot see (unit, golden and e2e tests stay the
gate; see `docs/testing.md`).

Six tasks in `tasks/<name>/` (workspace in `ws/`, goal in `goal.txt`, hidden tests in `hidden/`):
`code-simple`, `code-medium`, `code-hard` (graded by hidden unit tests; editing the visible tests
scores 0), `qa`, `content`, `review` (graded by constraint counts and keyword checks, so they are
a smoke test for quality, not a judge).

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
