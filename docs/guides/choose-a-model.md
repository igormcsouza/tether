# Choose a model: what to expect

*For: people picking a model to run tether with. After this page you can pick a model per job and know its limits.*

## The short answer

- Review a change: any model; `qwen3.5:9b` is fine.
- Fix a small bug: any model.
- Research on the web: Nemotron or Claude; set a search key (see [Set it up](#set-it-up)).
- Explain a codebase: Nemotron or Claude; `qwen3.5:9b` gives a shorter, correct overview.
- Multi-file implementation on a local GPU: `qwen3.5:9b` with the rules of [Write tasks a small model can finish](small-models.md) and `--verify`.
- Content/everyday writing: Claude Haiku (15 of 15 on the everyday ladder).

## The models

| Model | Runs on, cost | Good at | Weak at | Start with |
|---|---|---|---|---|
| `ollama/qwen3.5:9b` | Local, one 8 GB GPU, free, private | Review (found 3 of 4 planted bugs), small fixes, plans; Polyglot-Python 45 of 68 ([bench](../benchmarks.md)), ladder 19 of 24 ([ladder](../ladder/results.md)) | Web research (guesses URLs, one shaky claim in the check below), cases you did not state, judgement calls such as which clip to cut, slower (54–213 s per task below), often writes its answer as text and needs one reminder to call `done` | `--context-tokens 32768` (the default), `--verify`, the [small-models](small-models.md) rules |
| `ollama/qwen3.5:4b` | Local, free | Same ladder tiers as the 9B (13 of 24) | Leaves the steps more often | One-line edits only |
| `ollama/qwen2.5-coder:7b` | Local, free | Short single-file changes with `--verify` | 1 of 24 on the ladder, no thinking mode, writes whole files without reading | Not recommended for anything bigger |
| `nvidia/nvidia/nemotron-3-ultra-550b-a55b` | NVIDIA's free hosted API (needs a free key, 40 requests per minute, prompts leave your machine) | Strongest free model; finished all 5 tasks below, found all 4 planted bugs plus 3 real extras, cited research | Reads whole files, so it uses many tokens (206,338 prompt tokens to explain the codebase), ignores length limits (505 words when 300 were asked) | `rpm: 36` in providers.yaml, `--context-tokens 120000` |
| Claude Haiku | Paid, through the Claude CLI (`command` provider) or the Anthropic API | Everything below in 2–7 steps and 21–56 s; ladder 20 of 24 with tether against 18 of 24 plain Claude Code ([Haiku ladder](../ladder/claude-haiku.md)); everyday ladder 15 of 15 ([everyday ladder](../ladder/general.md)) | Tests it writes need a second look ([small-model guide](small-models.md)) | The cheapest model that finished every task here |
| Claude Sonnet, Claude Opus | Paid | Finished all 5 tasks below in 2–10 steps; the most careful answers (say what they did not check, name a runner-up). On tasks this size they did not do more than Haiku; measured once each, not on the ladder or the bench | Slower and costlier than Haiku for the same result on these tasks | Use them when Haiku's answer is not good enough |

## The same five tasks on every model

One check: 5 everyday tasks, one run per model, tether default settings, November 2026, no human follow-up. Tasks: web research on Python 3.14 free-threading; cut a YouTube Short from a finished video with a script; review a diff with 4 planted bugs; fix a bug a user reported; explain this codebase in 300 words.

| Task | qwen3.5:9b | nemotron | Haiku | Sonnet | Opus |
|---|---|---|---|---|---|
| Research | 22 / 213 | 19 / 99 | 7 / 37 | 8 / 44 | 6 / 56 |
| Short | 8 / 124 | 6 / 53 | 5 / 55 | 4 / 48 | 6 / 79 |
| Review (bugs found of 4) | 4 / 55 (3) | 2 / 21 (4) | 2 / 21 (4) | 2 / 13 (4) | 3 / 37 (4) |
| Bug fix | 12 / 54 | 14 / 40 | 7 / 34 | 10 / 52 | 5 / 37 |
| Explain | 8 / 66 | 15 / 51 | 5 / 33 | 7 / 44 | 6 / 58 |

- Every run finished with a usable result and every fix passed the tests.
- The difference is speed and judgement, not whether it finishes.
- One run per cell, so a difference of a few steps is noise.

The review task, as run with nemotron (first 3 of its 7 findings):

```bash
tether run --model nvidia/nvidia/nemotron-3-ultra-550b-a55b --tools bash --max-steps 15 "A teammate changed ratelimit.py (see git diff). Review the change like a senior engineer: list every real bug or risk, each with the line, why it is wrong, and the fix. Don't change any files."
```

```text
1. Line 12: time.time() → time.monotonic() (clock skew vulnerability)
2. Line 15: <= → < (off-by-one, allows max_calls+1 requests)
3. Line 23: wait_time() uses time.time() → use time.monotonic()
```

## Set it up

- Local models need Ollama ([Start here](../index.md)).
- Hosted models are declared in providers.yaml ([Model providers](../reference/providers.md)): NVIDIA is an `openai` kind entry; Claude through the CLI is a `command` entry.
- Web search without a key is often refused by DuckDuckGo (every search in the check above was). For research set `BRAVE_API_KEY`, `TAVILY_API_KEY` or `SEARXNG_URL`, or give the URLs in the task.

## When it goes wrong

- Read the session with `tether export <id>`.
- If a small model loops, make the task smaller once ([small-model guide](small-models.md#when-it-goes-wrong)), then move up one model.
- A free hosted model that fails with a usage-limit error is the provider, not tether: wait or switch.

```bash
tether run --model nvidia/nvidia/nemotron-3-ultra-550b-a55b --tools bash --max-steps 15 "A teammate changed ratelimit.py (see git diff). Review the change like a senior engineer: list every real bug or risk, each with the line, why it is wrong, and the fix. Don't change any files."
```

```text
1. Line 12: time.time() → time.monotonic() (clock skew vulnerability)
2. Line 15: <= → < (off-by-one, allows max_calls+1 requests)
3. Line 23: wait_time() uses time.time() → use time.monotonic()
```