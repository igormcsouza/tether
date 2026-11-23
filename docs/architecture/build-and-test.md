# Build and test tether

*For: people who want to contribute code or docs. After this page you know the checks a change must pass, how tether is tested without a model, and the habits that keep it small, fast and honest.*

Tether is a deterministic envelope around a random model. Changing the envelope can silently change what the model is shown, so the project tests behaviour at four levels, from cheap and exact to expensive and real. The authoritative version of these rules is [`AGENTS.md`](https://github.com/igormcsouza/tether/blob/main/AGENTS.md) and [`CONTRIBUTING.md`](https://github.com/igormcsouza/tether/blob/main/CONTRIBUTING.md); this page explains the reasoning.

## Set up

```sh
uv sync                                                          # environment
uv run ruff check . && uv run ruff format --check .              # lint and format (also formats Python in docs)
uv run mypy tether/                                              # types
uv run pytest --cov=tether --cov-report=term-missing --cov-fail-under=100
TETHER_E2E=1 uv run pytest e2e                                   # local only
```

Docs have their own check: `uv run mkdocs build --strict` must pass, because a renamed page breaks links elsewhere.

## The four levels of testing

| Level | What it proves | Needs a model? | Runs in CI? |
|---|---|---|---|
| **Unit tests**, 100% coverage | Each function does what it says, including the odd branches | no | yes |
| **Golden traces** (`tests/golden/`) | The exact messages the model sees at every step did not change | no (scripted replies) | yes |
| **End-to-end scenarios** (`e2e/`) | The real CLI, real processes and real Ollama behind a fault-injecting proxy behave | scripted ones no; some use one | no (local) |
| **Benchmarks** (`bench/`) | A change moved the number tether is judged by | yes | no |

### Golden traces: change what the model sees on purpose

A golden trace is a scripted session replayed through the real harness, multiplexer, tools, context assembly and folding. The test compares everything against a snapshot: the exact messages at every step, event types, token estimates, final result and files. A PR that changes nothing the model sees keeps every snapshot green. A PR that does shows a JSON diff in review.

```sh
UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py     # accept an intended change, then read the diff
```

Add a trace for every behaviour that must not regress. A fix without one is a fix that can quietly come undone.

### End-to-end: make the situation happen

`e2e/` starts the real `tether` in a throwaway workspace. A small proxy sits between tether and Ollama and can answer `429`, trickle a never-ending body, stall, or reply with a fixed tool call so no model is needed. Scenarios assert on what tether sent and recorded (requests, events, database state, exit codes, files), never on whether a model was clever. Success with a real model is only a warning, never a gate. A new feature or fix ships with a scenario; if a model would have to misbehave to trigger it, script the reply.

**Before merging a PR, run `TETHER_E2E=1 uv run pytest e2e` and put the result in the PR description.** CI cannot run it. Every failure is fixed, or the scenario is fixed, or the PR says why it is acceptable and what follows up. No unexplained red scenario is merged.

## Habits that keep tether what it is

**Spend no prompt tokens you cannot defend.** The fixed prompt is under 150 tokens and a test asserts it. A new per-turn note must be bounded in size, appear only when it applies and have a token-budget test. A note that models ignore is removed, not reworded (`tether stats` shows how often each notice is followed).

**Prefer the deterministic fix.** If the harness can repair a mistake without a model call (a quirk in a command, a missing newline, a stale read), repair it in code and keep the model's turn for thinking.

**Use what is there.** Before a new module, a new dependency or a new tool, check the existing primitives: `act`, the SQLite store, the FTS5 index, `mem`, `agent`. Heavy dependencies and vendor SDKs are not accepted; the standard library, `httpx` and `pyyaml` are enough.

**Failures say what to do next.** An error that ends in a traceback is a bug. An error says what happened, why, and the flag or command that fixes it.

**Measure before you build, and report honestly.**

- A behaviour change needs a bench or e2e delta in the PR body, even when it is flat. The line to end with is `north star: <before> -> <after> (runs, noise, run dir)`.
- Decide with a fast check first: replay recorded sessions offline, run the same exercise twice with a fixed seed and compare. Spend GPU time only on a change whose target metric moves.
- Compare the same exercises, paired, with a stated sample size. Twenty-four runs have a noise of about two or three passes, so a gain of one is not a result. Never judge by one run.
- Do not bench per line of code. Do not keep a wording tweak that did not move the number.

**Keep the docs true.** A change that adds or alters behaviour updates the docs in the same PR: README, the pages under `docs/`, a release note. The docs site is for people who *use* tether and has no bug history; known problems link to a GitHub issue labelled `known-issue`. Re-run the commands in the guides before a release and fix any output that changed.

## Decisions and the register

Read [the decisions register](decisions.md) before changing a default, a limit, a threshold or a trade-off, and cite the entry (`AD-12`) in your PR. If you introduce a decision, add it there in the same PR. If you disagree with one, open an issue; only the product owner changes a decision.

## Opening a pull request

One PR per task, a Conventional Commit title (`feat(scope): ... (#N)`, `fix(...)`, `docs(...)`), squash-merged to `main`. Merges and releases need the product owner's explicit yes each time. PyPI is published only from a GitHub Release, never from a push or tag.
