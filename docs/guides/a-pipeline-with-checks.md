# Run a pipeline where each stage has its own job

*For: people with a task that has an order: gather, then write, then check. After this page you can run a declarative pipeline, give each stage its own model, tools and gate, and read the results.*

A single long conversation gets confused. A **pipeline** splits the job into stages, each in its own clean session with its own tools and its own check, and passes a compact summary from one stage to the next.

## The job

Turn a list of changes into a short release note. Stage one only reads (and cannot write anything); stage two writes the file and must produce a non-empty `NOTE.md` before it may finish.

`changes.txt`:

```text
- csv export added to the reports page
- empty cart no longer crashes checkout
- install steps rewritten for Windows
```

`release-note.yaml`:

```yaml
name: release-note
stages:
  - id: facts
    model: ollama/qwen3.5:9b
    tools: [bash]
    sandbox: read-only          # this stage cannot change anything
    goal: "Read changes.txt and call done with the list of changes, one per line. Task: {{goal}}"
  - id: write
    model: ollama/qwen3.5:9b    # could be a different, stronger model
    tools: [bash, edit]
    verify: ["test -s NOTE.md"] # the stage cannot finish without this
    goal: "Using the changes from the previous stage, write NOTE.md: a three-sentence plain-English release note. Then call done."
```

## Run it

```bash
tether pipeline release-note.yaml "write the release note"
```

It finished in 19 seconds. `NOTE.md`:

```text
This release adds CSV export functionality to the reports page.
The checkout process now handles empty carts without crashing.
Install steps have been rewritten for better Windows compatibility.
```

`tether list` shows the three sessions: the pipeline itself and one per stage, each with its own status and step count.

```text
ses_61eda63a   COMPLETED  ...   2/2    write the release note      (the pipeline)
ses_3f575a5b   COMPLETED  ...   4/15   Using the changes from the previous stage, ...
ses_f6b0921b   COMPLETED  ...   2/15   Read changes.txt and call done with the list ...
```

## Why this helps

- **Clean context per stage.** The write stage did not see the reading stage's raw output, only a compact digest of its result (about 50 tokens), and it can query the earlier stage on demand.
- **A model per job.** Put a stronger or paid model only on the stage that needs it.
- **Narrowing only.** A stage can reduce the sandbox (`read-only`, fewer tools) but never widen what the pipeline allows.

## When it goes wrong

- **A stage ends `Max steps reached`.** Raise `max_steps` for that stage (or for the whole pipeline). There is no resume yet, so progress that lives in files is what you keep; re-run the stage by hand with `tether run --skill ...`.
- **A stage's gate keeps failing.** Run the gate command by hand; make the stage goal name the file it must produce.
- **Invalid manifest.** `Error: invalid pipeline ...` and exit code 1 name the field.

More: [Gates, memory, pipelines](../tutorial/workflows-and-telemetry.md#pipelines), [multi-agent](../tutorial/multi-agent.md).
