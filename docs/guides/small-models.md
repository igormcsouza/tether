# Write tasks a small model can finish

*For: people who hand tasks to tether on a small local model, and people choosing a model for a job. After this page you can write a task that a 9B model finishes, check that it really did, and tell whose fault a failed task is.*

A small model is a good typist and a careful rule follower. It is a weak planner. So the plan goes in the task text, and the model does one small thing at a time.

## The rules

1. **One edit per task.** One file, one place. Two changes are two tasks.
2. **Say where.** Name the file and the line numbers, and tell the model to view those lines first.
3. **Give a contract, not code.** Say what the function must return and show two or three examples. The model writes the body. If you already wrote the code, apply it yourself.
4. **Avoid line arithmetic.** New code goes in with `edit append <file>`, which needs no line numbers. To add lines in the middle, replace one short line with itself first and the new lines after it.
5. **Pass the edit as two arguments.** `cmd` is `edit replace <file> --lines A:B` and `stdin` is the final text of those lines. No diff marks, no code fences.
6. **One check that runs code.** Give one command that fails before the change and passes after it. Compare exact values. A `grep` for a word passes on broken code.
7. **Keep chores out.** Lint, types and the full test suite run after the task, by you or by `--verify`.
8. **Small step budget.** `--max-steps 8` to `12`. A task that needs more is two tasks.

## Example

A function forgets to add 32. This is `temps.py`:

```python
def to_fahrenheit(celsius):
    return celsius * 9 / 5
```

`check.py` fails now and passes after the fix:

```python
from temps import to_fahrenheit

assert to_fahrenheit(0) == 32
assert to_fahrenheit(100) == 212
assert to_fahrenheit(-40) == -40
print("ok")
```

The task, in `task.md`:

```text
You do ONE small edit. Follow the steps in order. Do nothing else.
1. View: `edit view temps.py --lines 1:2`. Line 2 returns the wrong value: it forgets to add 32.
2. Fix line 2 so `to_fahrenheit(0)` is 32 and `to_fahrenheit(100)` is 212. Call the `act` tool with two arguments: cmd = `edit replace temps.py --lines 2:2`, stdin = the corrected line (4 spaces of indentation).
3. Run `bash python3 check.py`. It prints `ok` -> call `act("done", stdin="fixed")`. It fails -> view line 2, fix it the same way, run the check again.
```

Run it:

```bash
tether run --model ollama/qwen3.5:9b --tools bash,edit --max-steps 8 --verify "python3 check.py" "$(cat task.md)"
```

```text
session ses_3353ac87
fixed
```

The session took 4 of its 8 steps. `--verify` ran `check.py` again before `done` was accepted, so `fixed` means the check passed, not that the model said so.

## What we saw, by model

| Model | Does well | Does badly |
|---|---|---|
| `ollama/qwen3.5:9b` | Follows numbered steps exactly. Writes a short function body from a contract. Writes a test from a described case. Fixes its own code when the check fails. | Counting lines after an edit. Long tasks with several goals. Side rules such as a line-length limit. It follows a wrong task as faithfully as a right one. |
| `ollama/qwen3.5:4b` | Single one-line edits. | Leaves the steps and does something else often enough that we do not rely on it. |
| Claude Haiku | Plans, tests written before the code, QA and review of a finished change. | Writing tasks for a smaller model: wrong line counts, checks that could not fail. Its tests need a second look. |
| Claude Sonnet, Claude Opus | No data yet for this way of working. | No data yet. |

This table changes as tether and the models change. A row is added only from runs we looked at.

## When it goes wrong

Read the session with `tether export <id>` and ask three questions, in this order:

1. **Did a tool refuse or mangle a correct command?** That is tether. Look for an error after a command that looks right, and report it.
2. **Did the model do what the task said, and the result is still wrong?** That is the task. Fix the text: a wrong line number, a missing step, a check that cannot fail.
3. **Did the model leave a clear task?** That is the model. Make the task smaller once. If it still leaves it, use a larger model for that task.

Common signs:

| Sign | Likely cause | What to do |
|---|---|---|
| Out of steps, many views and replaces of the same lines | Line arithmetic | Use `edit append`, or replace one short line |
| `done`, but the file is broken | The check did not run the code | Make the check import and call it |
| The check passes, the output is slightly off | The check compares part of the output | Compare the whole value |
| An edit command is refused | The edit text was put inside `cmd` | Say "two arguments: cmd and stdin" in the task |

More: [Fix a failing test with a local model](fix-a-failing-test.md), [Troubleshooting](../troubleshooting.md).