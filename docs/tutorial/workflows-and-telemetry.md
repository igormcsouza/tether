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

Prints per-model runs, pass rate, average steps, peak and total tokens, and friction counts (`nudge`, `loop_stall`, `cycle_stall`, `syntax_error`, `tool_error`, `gate_fail`), followed by the commands that cause the most friction. Pipeline root sessions are excluded so tokens are not double-counted.

## Post-mortem rules (`tether retro`)

```sh
tether retro "$SID"            # print a diff of proposed rules
tether retro "$SID" --apply    # append them
```

`retro` reads a finished session's friction trace (your `send` corrections, loop stalls, syntax/tool errors, failed gates), asks one model call for at most **2 rules of at most 30 tokens**, drops duplicates, and shows a unified diff of `SKILL.md`. `--apply` appends them under `## Learned Rules`, or pins them to project memory if the session used no skill. It never changes a live prompt.

## Example: course builder

The [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course) uses gates, a pipeline and telemetry. What we learned, by feature.

### Gates

- **Say what to DO next, not only what failed.** The gate output is what the model sees. `checks.py` ends its messages with the next step:

    ```python
    fail("topics without a video: 1.3, 2.1. Use yt-todo, yt-candidates <ref>, yt-save <n>.")
    ```

- **Gate scripts as files.** `verify: ['python3 checks.py plan']`, not an inline `awk '/Módulo/ ...'`: the sandbox path check blocks inline programs starting with `/` ([#31](https://github.com/igormcsouza/tether/issues/31), [Security and Sandbox](security-and-sandbox.md#example-awksed-programs-that-start-with)).
- **Fail closed.** A gate that reads a missing input file and finds nothing to check exits `0`. `checks.py videos` explicitly fails when `plan.md` has no modules.
- **An environment error counts as a failure.** If the gate command itself cannot run (script missing, sandbox error) it is reported as a failed gate, and 3 consecutive failures end the session `FAILED` ([#33](https://github.com/igormcsouza/tether/issues/33)). Run your gate by hand before the pipeline.

### Pipelines

```yaml
name: course
max_steps: 60            # default for every stage; a stage may set its own max_steps
stages:
  - {id: plan,   skill: planner,  goal: "{{goal}}"}
  - {id: videos, skill: searcher, goal: "Escolha 1 vídeo para cada tópico de plan.md"}
  - {id: course, skill: writer,   goal: "Monte course.md a partir de plan.md e dos vídeos escolhidos"}
```

Each stage takes its `verify` gates and tools from its skill, and its model from the skill's `model:` (a stage `model:` routes per stage).

- **Size `max_steps` to the work.** A 15-topic plan needed about 57 searcher steps (`yt-todo`, `yt-candidates`, `yt-save` per topic); with 50 the stage failed with 2 topics left.
- **There is no built-in resume** ([#35](https://github.com/igormcsouza/tether/issues/35)). Progress lives in files (`videos.md`), so re-run the stage's skill by hand; the tools skip finished topics:

    ```sh
    tether run --skill searcher "Escolha 1 vídeo para cada tópico de plan.md"
    ```

### Telemetry

List a session's commands from the database (the sandbox hides `.tether/` from the model, so run this in your own shell):

```sh
sqlite3 .tether/tether.db \
  "select step, event_type, tool_cmd from turns where session_id='$SID' and tool_cmd is not null order by step"
```

`turns.event_type` is one of `ok`, `nudge`, `loop_stall`, `cycle_stall`, `syntax_error`, `tool_error`, `gate_fail`, `completed`; the non-`ok` ones are what `tether stats` counts as friction. Model **reasoning is not recorded** (only the action and its output), so a "thinking" model that loops shows no visible cause ([#32](https://github.com/igormcsouza/tether/issues/32)).
