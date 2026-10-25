# Troubleshooting

*For: when something does not work. Find your symptom, read the cause, apply the fix.*

Entries are grouped by what you see. For problems that are known and not fixed yet, see the [known issues](https://github.com/igormcsouza/tether/issues?q=is%3Aissue+is%3Aopen+label%3Aknown-issue) on GitHub. To see what a session actually did, start with `tether read <id> --steps` and `tether stats`.

## The session ends badly

### `FAILED` with `Stalled: ... loop warnings` (exit code 4)

**Cause.** The model repeated a command, cycled through the same few, or kept reading one file over shifting line ranges without editing. The guard ended the session early instead of spending every step.

**Fix.** Make the goal name the file and the edit. Run `tether read <id> --steps` to see the loop. Try a stronger model. Raising `--max-steps` only repeats the loop.

### `FAILED` with `Max steps (N) reached without calling done`

**Cause.** The task needs more steps than allowed, or the model never found the way to finish.

**Fix.** Check `tether read <id> --steps`: if the work is done and the model keeps verifying, tell it to call `done` in the goal. If it needs more room, raise `--max-steps` (for a pipeline, per stage). `tether send <id> "keep going"` resumes a finished session with a fresh budget.

### `FAILED` with `Verification gate ... misconfigured`

**Cause.** The `--verify` command itself broke (sandbox violation, command not found, timeout), not your work. This fails fast and shows as `gate_error` in `tether stats`.

**Fix.** Run the gate command by hand in the workspace first and fix it. A gate that exits 0 when its input is missing checks nothing: make it fail closed. See [Gates](tutorial/workflows-and-telemetry.md#gates).

### `Worker error: ProviderError: ... unavailable after N attempts`

**Cause.** The model server timed out, was unreachable or kept answering 5xx. Tether retried twice with backoff.

**Fix.** Check the server is up and the model is loaded. A slow first call can need a larger `timeout` in `providers.yaml`. See [Model providers](reference/providers.md#entry-settings).

## The model misbehaves

### Many nudges in `tether stats`, or an empty reply with no tool call

**Cause.** The reply was not parsed into an action, or the server dropped an unparsable tool call (seen with `qwen3:8b` on Ollama).

**Fix.** Run `tether misses` to list the replies. Add a dialect for the format (a `dialects:` regex on the `command` provider, or a line in `tests/fixtures/dialects.jsonl`). Try `--param think=false`, another model or a newer Ollama.

### The model keeps re-reading a file, then writes invented content

**Cause.** Old tool output is folded after a few turns to save context, so a small model can forget what it read.

**Fix.** Raise `--fold-after`, or have the tool give one compact view right before the write that ends with the exact next call. See [Context and SQLite Store](reference/context-and-store.md#observation-folding-and-small-models).

### A long `edit write` is missing a section, or earlier content vanished

**Cause.** One very long generation can drop content, and `edit write` replaces the whole file (it reports what an overwrite removed).

**Fix.** Write one small file per section and join them with a tool, rewrite the complete file, or use `edit replace` for a range. See [Built-in Tools](tutorial/built-in-tools.md#example-course-builder).

### The model repeats a tool call with a value that was rejected

**Cause.** The tool or gate said what failed but not what to do.

**Fix.** Return the valid options and the next call in the message. See [Custom tools](tutorial/sdk-and-custom-tools.md#example-course-builder).

### A thinking model loops and the trace shows no reasoning

**Cause.** The model's reasoning is not recorded in the trace.

**Fix.** Inspect the commands with the [telemetry query](tutorial/workflows-and-telemetry.md#telemetry), or try a non-thinking model.

## Setup and providers

### `...` `` `NVIDIA_API_KEY` `` `is missing or rejected` (any `api_key_env` name)

**Cause.** The provider answered 401/403, or the variable named by `api_key_env` is unset or empty. Tether prints the name, never the value.

**Fix.** Export a valid key under that name. An empty variable fails the session before any request is sent.

### `Ollama model … not found; installed: …`

**Cause.** The model name is not pulled. Tether does not substitute another model unless you ask it to.

**Fix.** `ollama pull <model>`, fix the name, or set `TETHER_OLLAMA_FALLBACK=1` to opt in to a substitute.

### `Ollama … HTTP 500 … No user query found in messages` or `the prompt does not fit num_ctx`

**Cause.** The real prompt (code and test output run 1.3-1.5 tokens per 4 characters) outgrew `num_ctx`, so Ollama dropped the goal message and the chat template refused. Tether retries once with `num_ctx` doubled (up to 4x) and keeps the larger window.

**Fix.** If it still fails, lower `--context-tokens` or use a model with a bigger context window.

### `tether mcp` prints "MCP support is not installed"

**Cause.** The optional extra is missing.

**Fix.** `pip install "tether-sdk[mcp]"`. See [Use Tether Inside Your Harness](tutorial/agent-interface.md).

## Tools and skills

### `Error: bash is disabled` or `unknown command`

**Cause.** The tool is not enabled for this session. The message lists the tools that are.

**Fix.** Add it with `--tools bash,edit`, the SDK `tools=[...]` or the skill `tools:` list.

### `unknown command` for a tool defined in a skill's `tools.py`

**Cause.** A skill's own tools are opt-in like any other: the tool must also be listed in the skill's `tools:`. Loading the skill emits a `UserWarning` naming the unlisted ones.

**Fix.** Add its name to `tools:`. See [Skills](tutorial/skills.md#tools-py-and-the-tools-list).

### `.venv/bin/pytest` or another tool is "not found" inside `bash`

**Cause.** The sandbox hides your home directory. Tools on `PATH` under `$HOME` and a workspace virtualenv's interpreter are re-exposed read-only; anything else under `$HOME` is not visible.

**Fix.** Put the tool on `PATH`, or inside the workspace. See [Security and Sandbox](tutorial/security-and-sandbox.md).

### A gate or command with inline `awk`/`sed` is refused as a path outside the workspace

**Cause.** With no kernel sandbox (`bwrap`) available, tether checks commands by text and can mistake a program that starts with `/` for a path.

**Fix.** Install `bwrap` (the kernel enforces the boundary instead), or move the logic into a script. See [Security and Sandbox](tutorial/security-and-sandbox.md#example-awksed-programs-that-start-with).
