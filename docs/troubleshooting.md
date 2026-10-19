# Troubleshooting

Symptom, cause, fix. Most entries come from building the [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course) on small local models.

| Symptom | Cause | Fix |
|---|---|---|
| Model keeps running `edit view` on the same file, then writes invented data | Old observations fold after 2 turns ([#27](https://github.com/igormcsouza/tether/issues/27)) | Give it one compact tool view right before the write, ending with the exact next call. See [Context and SQLite Store](reference/context-and-store.md#observation-folding-and-small-models) |
| A long `edit write` is missing a whole section | One big generation drops content | Write one small file per section (`part-N.md`) and join them with a tool. [Same page](reference/context-and-store.md#observation-folding-and-small-models) |
| Earlier file content vanished after a second `edit write` | `edit write` replaces the whole file ([#34](https://github.com/igormcsouza/tether/issues/34)) | Tell the model to rewrite the complete file, or use `edit replace --lines`. See [Built-in Tools](tutorial/built-in-tools.md#example-course-builder) |
| Files contain a literal `\n` | Model sent escaped newlines in stdin | Fixed in v0.1.2 for `edit write`, `edit replace` and `done` |
| Tool with multi-word argument fails (`unexpected keyword argument`, wrong value) | Unquoted words were not joined | Fixed in v0.1.2. See [argument parsing](tutorial/sdk-and-custom-tools.md#argument-parsing-v012) |
| `Error: unknown command` for a tool defined in `tools.py` | The tool is not in the skill `tools:` list ([#24](https://github.com/igormcsouza/tether/issues/24)) | Add its name to `tools:`. See [Skills](tutorial/skills.md#tools-py-and-the-tools-list) |
| Model answers are not understood (many nudges in `tether stats`) | The reply format is not parsed into an action | Run `tether misses`, then add a dialect: paste the lines into `tests/fixtures/dialects.jsonl` or add a `dialects:` regex to `providers.yaml` |
| Gate with inline `awk`/`sed` is blocked as "absolute path outside workspace" | Fixed in v0.1.4 ([#31](https://github.com/igormcsouza/tether/issues/31)); older versions saw a program starting with `/` as a path | Upgrade, or move the logic into a script (`python3 checks.py ...`). See [Security and Sandbox](tutorial/security-and-sandbox.md#example-awksed-programs-that-start-with) |
| `Ollama model … not found; installed: …` | The model name is not pulled; Tether no longer substitutes another one ([#21](https://github.com/igormcsouza/tether/issues/21)) | `ollama pull <model>`, fix the name, or set `TETHER_OLLAMA_FALLBACK=1` to opt in to a substitute |
| `tether mcp` prints "MCP support is not installed" | The optional extra is missing | `pip install "tether-sdk[mcp]"`. See [Use Tether Inside Your Harness](tutorial/agent-interface.md) |
| Gate exits 0 although work is missing | Missing input file means nothing to check | Make the gate fail closed. See [Gates](tutorial/workflows-and-telemetry.md#gates) |
| Session `FAILED` after 3 gate failures, none of them real | A gate environment error counts as a failure ([#33](https://github.com/igormcsouza/tether/issues/33)) | Run the gate command by hand first |
| Model repeats a tool call with a rejected value | Gate or tool message says what failed, not what to do | Return the valid options and the next call in the message. See [Custom Tools](tutorial/sdk-and-custom-tools.md#example-course-builder) |
| A pipe-delimited file gets extra or shifted columns | A delimiter (` | `) appeared inside a value | Sanitize values in the tool that writes the file |
| Pipeline stage ends "Max steps reached" | `max_steps` too small for the work ([#35](https://github.com/igormcsouza/tether/issues/35)) | Raise `max_steps` (pipeline or stage), or re-run the stage's skill by hand. See [Pipelines](tutorial/workflows-and-telemetry.md#pipelines) |
| A thinking model loops and the trace shows no reasoning | Reasoning is not recorded ([#32](https://github.com/igormcsouza/tether/issues/32)) | Inspect the commands with the [telemetry query](tutorial/workflows-and-telemetry.md#telemetry); try a non-thinking model |

## Known limitations

- [#24](https://github.com/igormcsouza/tether/issues/24) skill `tools.py` tools must also be listed in `tools:`.
- [#27](https://github.com/igormcsouza/tether/issues/27) observation folding hurts small models.
- [#32](https://github.com/igormcsouza/tether/issues/32) model reasoning is not in the trace.
- [#33](https://github.com/igormcsouza/tether/issues/33) gate infrastructure errors count toward the 3-failure abort.
- [#34](https://github.com/igormcsouza/tether/issues/34) no `edit append`.
- [#35](https://github.com/igormcsouza/tether/issues/35) no pipeline resume; one `max_steps` for the whole pipeline unless set per stage.

## Model notes

In this experiment `gemma4:e4b` needed much more scaffolding (numbered-candidate tools, joined views, tight gates) than `qwen3.5:9b`. These were single runs on a small sample, so treat this as an observation, not a benchmark.
