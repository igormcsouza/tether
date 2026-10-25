# CLI reference

*For: people and agents calling the `tether` command. After this page you know every subcommand, flag and exit code.*

The `tether` command is the primary entry point for running, inspecting, and controlling headless LLM sessions. Add `--json` (where a command lists it) for machine-readable output.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Completed successfully |
| `1` | Usage error (bad arguments, missing required flags) |
| `2` | Waiting for input (`WAITING_INPUT`) |
| `3` | Verification gate failed |
| `4` | Max steps reached or stalled |
| `5` | Worker or provider error |

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
| `--context-tokens` | Context token budget (default 8192) |
| `--fold-after` | Fold observations older than N turns (default 2) |
| `--db` | SQLite DB path (default .tether/tether.db) |
| `--param` | Model request parameter, repeatable (e.g., `--param temperature=0 --param think=false`) |
| `--output-schema` | JSON Schema file; the `done` deliverable must validate or `done` is rejected |
| `--result-file` | Write the deliverable here, not to stdout |
| `--json` | Machine-readable JSON output |

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
| `--context-tokens` | Context token budget (default 8192) |
| `--fold-after` | Fold observations older than N turns (default 2) |
| `--result-file` | Write the deliverable here, not to stdout |
| `--json` | Machine-readable JSON output |

```bash
tether pipeline pipelines/research.yaml "Research topic: Rust async patterns" --json
```

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