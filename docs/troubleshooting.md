# Troubleshooting

*For: when something does not work. Find your symptom, read the cause, apply the fix. Where a problem was reported and fixed, the entry links to the GitHub issue so you can follow the history.*

Entries are grouped by what you see. For problems that are known and not fixed yet, see the [known issues](https://github.com/igormcsouza/tether/issues?q=is%3Aissue+is%3Aopen+label%3Aknown-issue) on GitHub. To see what a session actually did, start with `tether read <id> --steps` and `tether stats`.

## The session ends badly

### `WAITING_INPUT` with `[STUCK ...]` (exit code 2)

*Tracked in [#92](https://github.com/igormcsouza/tether/issues/92) (resolved), [#163](https://github.com/igormcsouza/tether/issues/163) (resolved).*

**Cause.** The model repeated a command, cycled through the same few, or kept reading one file over shifting line ranges without editing. Or the same test kept failing after edits. The harness restarted it from a short description of the state twice and it was still stuck, so it stopped and handed the task back instead of spending every step.

Before the guard ends the session it adds one `[WRAP UP]` turn: a session that only read is asked for its final answer, one that already changed something is asked to call `done` with what is done and what is left. If the model answers, the session completes normally; if it repeats the command again, the session restarts from a fresh, short description of the state (files as they are, last failing output, counts of what was tried), twice at most, then ends `WAITING_INPUT` with that description as its result.

With `--verify` gates configured, a stall after a change whose gates all pass ends `COMPLETED` instead ("Finished by the harness"), because the work is verified.

If the model wrote its answer as plain text instead of passing it to `done` (common with small models on questions), the result ends with that reply under "The model's last reply, never confirmed with `done`". It is often the answer you wanted.

**Fix.** Read the `[STUCK]` result: it says what was tried. Refine the goal (name the file and the edit) and `tether send <id> "<guidance>"`, or try a stronger model. Raising `--max-steps` only repeats the loop.

### `WAITING_INPUT` with `[STUCK: out of steps (N) ...]` (exit code 2)

*Tracked in [#75](https://github.com/igormcsouza/tether/issues/75) (resolved), [#169](https://github.com/igormcsouza/tether/issues/169) (resolved), [#177](https://github.com/igormcsouza/tether/issues/177) (resolved).*

**Cause.** The task needs more steps than allowed, or the model never found the way to finish. The session is handed back instead of failed, so you can continue it.

The result is never bare: it lists the last change commands and, with `--verify`, whether the gates pass now. A run that stopped with passing gates already holds a usable result in the workspace.

A session whose last test run passed after its final change ends `COMPLETED` instead ("Finished by the harness"), even without `--verify`.

**Fix.** Check `tether read <id> --steps`: if the work is done and the model keeps verifying, tell it to call `done` in the goal. A bare `done` is enough: it ends the session with the result `Done.` once the gates pass. If it needs more room, raise `--max-steps` (for a pipeline, per stage). `tether send <id> "keep going"` resumes the session with a fresh budget.

### `FAILED` with `Verification gate ... misconfigured`

*Tracked in [#33](https://github.com/igormcsouza/tether/issues/33) (resolved), [#82](https://github.com/igormcsouza/tether/issues/82) (resolved), [#304](https://github.com/igormcsouza/tether/issues/304) (resolved).*

**Cause.** The `--verify` command itself broke (sandbox violation, command not found, timeout), not your work. This fails fast and shows as `gate_error` in `tether stats`.

**Fix.** Run the gate command by hand in the workspace first and fix it. A gate that exits 0 when its input is missing checks nothing: make it fail closed. See [Gates](guides/advanced/gates-memory-telemetry.md#gates).

### `Worker error: ProviderError: ... unavailable after N attempts`

*Tracked in [#70](https://github.com/igormcsouza/tether/issues/70) (resolved), [#88](https://github.com/igormcsouza/tether/issues/88) (resolved), [#305](https://github.com/igormcsouza/tether/issues/305) (resolved).*

**Cause.** The model server timed out, was unreachable or kept answering 5xx. Tether retried twice with backoff.

**Fix.** Check the server is up and the model is loaded. A slow first call can need a larger `timeout` in `providers.yaml`. See [Model providers](reference/providers.md#entry-settings).

### Nothing is printed for a long time

*Tracked in [#90](https://github.com/igormcsouza/tether/issues/90) (resolved).*

**Cause.** The model is still answering: a local model may be loading into memory on the first call, and a thinking model can take a minute per step. Tether prints nothing to stdout until the deliverable is ready.

**Fix.** Watch stderr: an animated `waiting for <model> ...` line shows the run is alive, and `--verbose` prints one line per finished step. No dots in a terminal means the run is not foreground or stderr is redirected. To inspect a run from another shell use `tether read <id> --steps`. See [`tether run`](reference/cli.md#tether-run).

## The model misbehaves

### Many nudges in `tether stats`, or an empty reply with no tool call

*Tracked in [#135](https://github.com/igormcsouza/tether/issues/135) (resolved), [#195](https://github.com/igormcsouza/tether/issues/195) (resolved).*

**Cause.** The reply was not parsed into an action, or the server dropped an unparsable tool call (seen with `qwen3:8b` on Ollama).

**Fix.** Run `tether misses` to list the replies. Add a dialect for the format (a `dialects:` regex on the `command` provider, or a line in `tests/fixtures/dialects.jsonl`). Try `--param think=false`, another model or a newer Ollama.

### The model keeps re-reading a file, then writes invented content

*Tracked in [#27](https://github.com/igormcsouza/tether/issues/27) (open), [#205](https://github.com/igormcsouza/tether/issues/205) (open).*

**Cause.** Old tool output is folded after a few turns to save context, so a small model can forget what it read.

**Fix.** Raise `--fold-after`, or have the tool give one compact view right before the write that ends with the exact next call. See [Context and SQLite Store](reference/context-and-store.md#observation-folding-and-small-models).

### A long `edit write` is missing a section, or earlier content vanished

*Tracked in [#34](https://github.com/igormcsouza/tether/issues/34) (resolved), [#267](https://github.com/igormcsouza/tether/issues/267) (resolved).*

**Cause.** One very long generation can drop content, and `edit write` replaces the whole file (it reports what an overwrite removed).

**Fix.** Write the file in parts with `edit append <path>` (each part in `stdin`), rewrite the complete file, or use `edit replace` for a range. See [Built-in Tools](guides/basic/built-in-tools.md#example-course-builder).

### The model repeats a tool call with a value that was rejected

**Cause.** The tool or gate said what failed but not what to do.

**Fix.** Return the valid options and the next call in the message. See [Custom tools](guides/advanced/sdk-and-custom-tools.md#example-course-builder).

### A thinking model loops and the trace shows no reasoning

*Tracked in [#32](https://github.com/igormcsouza/tether/issues/32) (resolved).*

**Cause.** A thinking model can spend its whole window reasoning and never emit a command.

**Fix.** Read what it thought with `tether read <id> --thinking` (stored for you, never sent back to the model). Tether already bounds thinking per turn and asks again once with thinking off; if it still loops, set a smaller `--param num_predict=...` or try a non-thinking model. See [Thinking and sampling](concepts/thinking-and-sampling.md).

## Setup and providers

### `...` `` `NVIDIA_API_KEY` `` `is missing or rejected` (any `api_key_env` name)

*Tracked in [#71](https://github.com/igormcsouza/tether/issues/71) (resolved).*

**Cause.** The provider answered 401/403, or the variable named by `api_key_env` is unset or empty. Tether prints the name, never the value.

**Fix.** Export a valid key under that name. An empty variable fails the session before any request is sent.

### `Ollama model … not found; installed: …`

**Cause.** The model name is not pulled. Tether does not substitute another model unless you ask it to.

**Fix.** `ollama pull <model>`, fix the name, or set `TETHER_OLLAMA_FALLBACK=1` to opt in to a substitute.

### `Ollama … HTTP 500 … No user query found in messages` or `the prompt does not fit num_ctx`

*Tracked in [#145](https://github.com/igormcsouza/tether/issues/145) (resolved).*

**Cause.** The real prompt (code and test output run 1.3-1.5 tokens per 4 characters) outgrew `num_ctx`, so Ollama dropped the goal message and the chat template refused. Tether retries once with `num_ctx` doubled (up to 4x) and keeps the larger window.

**Fix.** If it still fails, lower `--context-tokens` or use a model with a bigger context window.

### `tether mcp` prints "MCP support is not installed"

**Cause.** The optional extra is missing.

**Fix.** `pip install "tether-sdk[mcp]"`. See [Use Tether Inside Your Harness](guides/advanced/use-from-your-agent-mcp.md).

### bwrap is installed but blocked (Ubuntu 24.04+)

*Tracked in [#311](https://github.com/igormcsouza/tether/issues/311) (resolved).*

**Symptom.** `tether doctor` shows `FAIL bwrap ... cannot create namespaces`, and a write session refuses to start with `Sandbox unavailable: bwrap is installed (...) but the kernel refuses it`.

**Cause.** AppArmor restricts unprivileged user namespaces on Ubuntu 24.04+, so `bwrap` is present but the kernel will not let it create the sandbox.

**Fix.** Any one of:

- Lift the restriction: `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`, and persist it in `/etc/sysctl.d/`.
- Run inside a container and set `TETHER_SANDBOX=container`.
- Pass `--allow-unsandboxed` (SDK/MCP: `allow_unsandboxed=True`) to run with command checks only.

## Tools and skills

### `Error: bash is disabled` or `unknown command`

**Cause.** The tool is not enabled for this session. The message lists the tools that are.

**Fix.** Add it with `--tools bash,edit`, the SDK `tools=[...]` or the skill `tools:` list.

### `unknown command` for a tool defined in a skill's `tools.py`

**Cause.** A skill's own tools are opt-in like any other: the tool must also be listed in the skill's `tools:`. Loading the skill emits a `UserWarning` naming the unlisted ones.

**Fix.** Add its name to `tools:`. See [Skills](guides/basic/skills.md#tools-py-and-the-tools-list).

### `.venv/bin/pytest` or another tool is "not found" inside `bash`

*Tracked in [#76](https://github.com/igormcsouza/tether/issues/76) (resolved).*

**Cause.** The sandbox hides your home directory. Tools on `PATH` under `$HOME` and a workspace virtualenv's interpreter are re-exposed read-only; anything else under `$HOME` is not visible.

**Fix.** Put the tool on `PATH`, or inside the workspace. See [Security and Sandbox](guides/advanced/security-and-sandbox.md).

### A gate or command with inline `awk`/`sed` is refused as a path outside the workspace

*Tracked in [#125](https://github.com/igormcsouza/tether/issues/125) (resolved).*

**Cause.** With no kernel sandbox (`bwrap`) available, tether checks commands by text and can mistake a program that starts with `/` for a path.

**Fix.** Install `bwrap` (the kernel enforces the boundary instead), or move the logic into a script. See [Security and Sandbox](guides/advanced/security-and-sandbox.md#example-awksed-programs-that-start-with).
