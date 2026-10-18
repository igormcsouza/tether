# Gates, Memory, Pipelines & Telemetry

Everything on this page is deterministic harness behavior: it costs **0 static prompt tokens** until it fires.

## Verification gates (`--verify`)

A gate is a shell command that must exit `0` before `done` can complete the session. It runs inside the session's `SandboxPolicy`.

```sh
tether run --tools bash,edit --verify "pytest -q" --verify "ruff check ." "Fix the failing test"
```

If a gate fails, `done` is rejected and a `[VERIFICATION GATE FAILED: ...]` observation is injected so the model can fix the problem and retry. After repeated consecutive failures the session ends `FAILED`. Gates can also come from `Harness(verify=[...])` or a Skill's `verify:` frontmatter list.

## Asking for input (`done --ask`)

The agent can pause and ask a question instead of finishing:

```text
act("done --ask", stdin="Which database should I target?")
```

The session moves to `WAITING_INPUT` and the worker process exits. `tether wait` returns as soon as a session is waiting. Answer with `send`, which resumes the worker from SQLite:

```sh
SID=$(tether run --headless "Set up the schema (ask me if unsure)")
tether wait "$SID"          # shows the question
tether send "$SID" "SQLite"  # resumes the session
```

## Project memory (`mem --project`)

Session pins disappear with the session. Project pins live under the workspace-wide `__project__` scope and are visible to every session:

```text
act("mem pin --project test_cmd 'uv run pytest -q'")
act("mem search --project 'test command'")
```

`mem search --project` runs BM25 over pins, final deliverables and observations from **all** sessions in the database.

## Pipelines (`tether pipeline`)

A pipeline is a YAML file of stages. Each stage runs in its own isolated session, optionally with its own model, tools, `verify` gates and `sandbox` (a stage can only narrow the sandbox, never widen it). Later stages receive a ~50-token digest of earlier stages and can use `agent query` / `agent read` on them. `{{goal}}` in a stage goal is replaced by the pipeline goal.

```yaml
name: write-and-check
stages:
  - id: write
    model: ollama/qwen3.5:9b
    tools: [bash]
    verify: ["test -f note.txt"]
    goal: "Write note.txt containing 'alpha'. Goal: {{goal}}"
  - id: check
    sandbox: read-only
    tools: [bash]
    goal: "Read note.txt and call done with its content."
```

```sh
tether pipeline workflow.yaml "demo"            # foreground
tether pipeline workflow.yaml --headless "demo" # detached
```

Each stage needs a `goal`. Invalid manifests print `Error: invalid pipeline ...` and exit 1. See [Multi-Agent](multi-agent.md) for more.

## Telemetry (`tether stats`)

```sh
tether stats [--model <m>] [--skill <s>] [--limit <n>]
```

Prints per-model runs, pass rate, average steps, peak and total tokens, and friction counts (`nudge`, `loop_stall`, `syntax_error`, `tool_error`, `gate_fail`), followed by the commands that cause the most friction. Pipeline root sessions are excluded so tokens are not double-counted.

## Post-mortem rules (`tether retro`)

```sh
tether retro "$SID"            # print a diff of proposed rules
tether retro "$SID" --apply    # append them
```

`retro` reads a finished session's friction trace (your `send` corrections, loop stalls, syntax/tool errors, failed gates), asks one model call for at most **2 rules of at most 30 tokens**, drops duplicates, and shows a unified diff of `SKILL.md`. `--apply` appends them under `## Learned Rules`, or pins them to project memory if the session used no skill. It never changes a live prompt.
