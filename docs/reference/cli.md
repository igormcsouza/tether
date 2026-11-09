# CLI reference

*For: people and agents calling the `tether` command. After this page you know every subcommand, flag and exit code.*

The `tether` command is the primary entry point for running, inspecting, and controlling headless LLM sessions. Add `--json` (where a command lists it) for machine-readable output.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Completed successfully |
| `1` | Usage error (bad arguments, missing required flags) |
| `2` | Waiting for input (`WAITING_INPUT`), including a session that is stuck or out of steps and was handed back |
| `3` | Verification gate failed |
| `5` | Worker or provider error |
| `6` | `wait` timed out with sessions still `RUNNING` or `PENDING` (message on stderr) |

If a headless worker dies before it starts (exit `5`), the session is marked `FAILED` with `Worker died (pid N) before starting`, and the failure names the worker log at `<db dir>/workers/<id>.log`, which keeps the worker's stdout and stderr. Read that file to see why it died.

A `wait` with `--timeout` (default 120 seconds) that expires while sessions are still `RUNNING` or `PENDING` exits `6` and prints `timed out; still RUNNING: <ids>` to stderr.

## tether run

Start a new headless session with a goal and optional tools, model, or harness. Use this to launch autonomous tasks that run to completion or until a gate pauses them.

```bash
tether run "your goal here" [flags]
```

| Flag | Meaning |
|------|---------|
| `--headless` | Run detached in background and print session ID |
| `--model` | Model identifier (e.g., `ollama/qwen3.5:9b`, `openai/gpt-4o-mini`) |
| `--skill` | Skill name from `./skills/` or `~/.tether/skills/` |
| `--tools` | Comma-separated tools (e.g., `web,mem,bash` or `all`) |
| `--verify` | Deterministic verification gate command to run before `done` (repeatable) |
| `--sandbox` | Deterministic sandbox profile |
| `--no-network` | Disable network inside the bash sandbox (requires bwrap; fails closed without it) |
| `--max-steps` | Maximum reasoning steps |
| `--max-tokens` | Token budget (prompt + completion); pauses as WAITING_INPUT (exit 2) when reached |
| `--context-tokens` | Context token budget (default 32768) |
| `--fold-after` | Fold observations older than N turns (default 2), once the history fills half the context; raise it for long tasks |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--param` | Model request parameter, repeatable (e.g., `--param temperature=0 --param think=false`) |
| `--output-schema` | JSON Schema file; the `done` deliverable must validate or `done` is rejected |
| `--result-file` | Write the deliverable here, not to stdout |
| `--worktree` | Run in a git worktree on branch `tether/<id>`; the run commits its changes there when it stops |
| `--worktree-from` | Base ref for `--worktree` (default HEAD) |
| `--setup` | Shell command run in the worktree before the model starts; runs outside the sandbox, not offered over MCP |
| `--verbose`, `-v` | Print one line per step to stderr, e.g. `[step 3] edit view foo.py (2.1s, 812 tok)` |
| `--json` | Machine-readable JSON output |

**Progress feedback.** A foreground run shows it is alive without any flag: when stderr is a terminal, an animated `waiting for ollama/qwen3.5:9b ...` line (then `step 3 · bash pytest -q ...`) is redrawn until the run ends and erased when it does. The first model call can take a while, because a local model may still be loading into memory. The dots go to stderr only, never to stdout, and are off with `--json`, with `--headless` and when stderr is a pipe or a file. `--verbose` adds one permanent stderr line per step (also in pipes and logs); stdout still carries only the deliverable.

```bash
tether run "Summarize the README in 3 bullets" --model openai/gpt-4o-mini --tools web,mem --json
```

## tether pipeline

Execute a declarative pipeline from a YAML manifest with a root goal. Use this for reproducible, multi-stage workflows defined in configuration.

```bash
tether pipeline path/to/pipeline.yaml "root goal" [flags]
```

| Flag | Meaning |
|------|---------|
| `--headless` | Run detached in background and print session ID |
| `--model` | Default fallback model when a stage omits `model` |
| `--sandbox` | Root deterministic sandbox profile (stages can only narrow) |
| `--no-network` | Disable network inside the bash sandbox (requires bwrap; fails closed without it) |
| `--max-steps` | Default max reasoning steps per stage |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--context-tokens` | Context token budget (default 32768) |
| `--fold-after` | Fold observations older than N turns (default 2), once the history fills half the context; raise it for long tasks |
| `--result-file` | Write the deliverable here, not to stdout |
| `--json` | Machine-readable JSON output |

```bash
tether pipeline pipelines/research.yaml "Research topic: Rust async patterns" --json
```

### Resume a failed pipeline

```bash
tether pipeline --resume <pipeline_session_id> [--json] [--result-file F]
```

Re-runs the first stage that is not `COMPLETED` (a failed or waiting one) and every stage after it; earlier completed stages are reused. The root sandbox and model come from the stored run, so `--model`, `--sandbox`, `--no-network`, `--max-steps`, `--context-tokens` and `--fold-after` are ignored. A bad flag combination, an unknown id, a `RUNNING` pipeline, or a missing or invalid manifest exits `1`; a `COMPLETED` pipeline prints a note and exits `0`. The stage list is read from the stored run, but the manifest must still exist and parse at its original path. Runs made before this change have no stored path and cannot be resumed.

## tether status

Show the current state of a session (running, paused, completed, failed). Use this to check progress without reading the full event log.

```bash
tether status <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether status ses_abc123 --json
```

## tether read

Print the full event transcript of a session. Use this to review what the agent did, step by step.

```bash
tether read <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--digest` | Show compact ~50-token digest card |
| `--steps` | Show step-by-step work log |
| `--thinking` | Show the stored model thinking per step (never sent back to the model) |
| `--full` | Show the full final result (the default) |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether read ses_abc123 --steps
```

## tether query

Search a session's event log for keywords. Use this to find specific tool calls, decisions, or errors without reading the entire transcript.

```bash
tether query <session_id> <query...> [flags]
```

| Flag | Meaning |
|------|---------|
| `--top` | Top K chunks to return |
| `--db` | SQLite DB path (default .tether/tether.db) |

```bash
tether query ses_abc123 "tool call" --top 10
```

## tether send

Send a follow-up instruction to a running or paused session. Use this to steer an agent mid-run or respond to a `WAITING_INPUT` pause.

```bash
tether send <session_id> <message...> [flags]
```

| Flag | Meaning |
|------|---------|
| `--headless` | Resume in background if completed |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether send ses_abc123 "Focus only on the authentication module" --json
```

## tether wait

Block until one or more sessions reach a terminal state (completed, failed, or paused). Use this in scripts to synchronize parallel runs.

```bash
tether wait <session_id...> [flags]
```

| Flag | Meaning |
|------|---------|
| `--timeout` | Maximum seconds to wait |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether wait ses_abc123 ses_def456 --timeout 120 --json
```

## tether stop

Request graceful termination of a running session. Use this to cancel a run that is stuck or no longer needed.

```bash
tether stop <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether stop ses_abc123 --json
```

## tether list

List all known sessions with their status, goal, and timestamps. Use this to get an overview of past and current runs.

```bash
tether list [flags]
```

| Flag | Meaning |
|------|---------|
| `--limit` | Maximum sessions to show |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether list --limit 20 --json
```

## tether stats

Show aggregate statistics across all sessions (counts by status, total steps, token usage). Use this for a quick health check of your workload.

```bash
tether stats [flags]
```

| Flag | Meaning |
|------|---------|
| `--model` | Filter by model identifier |
| `--skill` | Filter by skill name |
| `--limit` | Max recent sessions to analyze |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether stats --model openai/gpt-4o-mini --json
```

## tether retro

Generate a retrospective summary of a completed session (what worked, what didn't, suggestions). Use this to learn from past runs and improve prompts or pipelines.

```bash
tether retro <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--apply` | Write rules (SKILL.md or project pin) |
| `--model` | Model for the single LLM pass |
| `--db` | SQLite DB path (default .tether/tether.db) |

```bash
tether retro ses_abc123 --model openai/gpt-4o-mini --apply
```

## tether events

Stream raw events from a session in real time. Use this for live monitoring or piping into other tools.

```bash
tether events <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--follow` | Stream until the session ends |
| `--db` | SQLite DB path (default .tether/tether.db) |

```bash
tether events ses_abc123 --follow
```

## tether diff

Show what a session changed in its files, against the first bytes the session saw. New files show as added from empty. Current contents are read from disk.

```bash
tether diff <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--stat` | Added/removed line counts per file |
| `--db` | SQLite DB path (default .tether/tether.db) |

```bash
tether diff ses_abc123 --stat
```

## tether misses

Show tool calls that failed or returned errors across sessions. Use this to debug recurring tool failures.

```bash
tether misses [session_id] [flags]
```

| Flag | Meaning |
|------|---------|
| `--model` | Only sessions of this model |
| `--limit` | Max replies (default 20) |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--json` | Machine-readable JSON output |

```bash
tether misses --limit 20 --json
```
## tether export

Print a session as a Markdown transcript: goal, steps with commands and outputs, result.

```bash
tether export <session_id> [flags]
```

| Flag | Meaning |
|------|---------|
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--out` | Write to this file instead of stdout |

```bash
tether export ses_abc123 --out session.md
```



## tether doctor

Check Ollama is reachable, the model is pulled, bwrap is installed, providers.yaml is valid, and the session DB opens. Shows what to fix if anything is broken.

```bash
tether doctor [flags]
```

| Flag | Meaning |
|------|---------|
| `--model` | Model to check (default ollama/qwen3.5:9b) |
| `--db` | SQLite DB path (default .tether/tether.db) |

```bash
tether doctor --model ollama/qwen3.5:9b
```

## tether mcp

Start an MCP (Model Context Protocol) server that exposes tether sessions as tools. Use this to let other agents or IDEs invoke tether runs.

```bash
tether mcp [flags]
```

| Flag | Meaning |
|------|---------|
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--workspace` | Workspace root (default: current directory) |

```bash
tether mcp --workspace /path/to/project
```
## tether replay

Re-run a session's goal with its saved setup and compare the two runs.

```
tether replay SESSION_ID [--model M] [--max-steps N] [--db PATH] [--json]
```

- The replay runs in the current directory with the original's tools, skill, sandbox profile and network, output_schema and params. There is no workspace copy, so `cd` to the right place first.
- Verify gates are not stored, so a replay runs without them.
- The replay is recorded as a child of the original (`parent_id`), so `tether list` shows it under the original.
- `--model` and `--max-steps` override the original's values. `--max-steps` must be at least 1.
- `--db` points at the database file, as for the other subcommands.
- Exit `0` once the comparison prints, even if the replay FAILED (the status row shows it). Exit `1` if the session is unknown, still RUNNING or WAITING_INPUT, or the harness raises.

Text output:

```
replay of ses_abc12345 -> ses_def67890
                original   replay
model           fake/a     fake/a
status          COMPLETED  COMPLETED
steps           1          1
tokens          120        118
wall_s (approx) 0.4        0.3
```

`--json` prints `{"original": {...}, "replay": {...}}`, where each row has `id`, `model`, `status`, `steps`, `tokens` and `wall_s`.
