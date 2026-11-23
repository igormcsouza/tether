# Review and debug a session

*For: anyone who wants to know what a session actually did, or why it went wrong. After this page you can read every step, see the files it changed, export a transcript, spot patterns across runs and replay a task on another model.*

A model's final answer is only the last line of the story. Tether stores everything, so you can read the rest. This page uses one real session: Nemotron writing a word-count script ([the run from the start pages](../../start/script-with-nemotron.md)), id `ses_ed3a5a1c`.

## 1. Where is it, and how did it end?

```sh
tether status ses_ed3a5a1c
```

```text
ID             STATUS        MODEL                  STEP    PEAK_TOK  LAST_CMD
ses_ed3a5a1c   COMPLETED     nvidia/nvidia/nemotron-3-ultra-550b-a55b 6/20   1415      done
sandbox: bwrap
```

`STEP 6/20` is steps used out of the maximum, `PEAK_TOK` the biggest prompt the model saw. A small peak is good: it means the context stayed small.

## 2. What did it do, step by step?

```sh
tether read ses_ed3a5a1c --steps
```

Each step shows the command and the output the model saw (trimmed here):

```text
[step 1] cat > sample.txt << 'EOF' ...        [exit 0: no output] Command succeeded.
[step 2] cat > wordcount.py << 'EOF' ...      [exit 0: no output] Command succeeded.
[step 3] python3 wordcount.py sample.txt      the 5 / quick 4 / fox 4 / dog 3 / a 3
```

This is the first thing to read when a result looks wrong. Most surprises show up as a command that failed three steps earlier.

Two more views of the same data:

```sh
tether read ses_ed3a5a1c --digest      # a 50-token summary, what a parent agent would see
tether read ses_ed3a5a1c --thinking    # the model's own reasoning per step, if it has one
```

Thinking is stored for you only. It is never sent back to the model, which keeps the prompt small.

## 3. What did it change?

```sh
tether diff ses_ed3a5a1c
```

```text
--- a/sample.txt
+++ b/sample.txt
@@ -0,0 +1,2 @@
+The quick brown fox jumps over the lazy dog. The dog was not amused by the fox's quick movements.
+A quick fox and a lazy dog - what a classic tale! The quick brown fox jumped again and again.
--- a/wordcount.py
+++ b/wordcount.py
@@ -0,0 +1,32 @@
+#!/usr/bin/env python3
...
```

Tether keeps the first version of every file the session touched, so `diff` works even when the folder is not a git repository. It also names files that changed through something tether could not follow, such as a background process.

## 4. Hand it to someone else

```sh
tether export ses_ed3a5a1c > session.md
```

```text
# Session ses_ed3a5a1c

- Goal: Create wordcount.py: a script that takes a text file path and prints the 5 most common words...
- Model: nvidia/nvidia/nemotron-3-ultra-550b-a55b
- Status: COMPLETED
- Steps: 6

## Step 1
...
```

A Markdown transcript you can paste into an issue or a pull request. For tools, `tether events <id>` prints the same steps as one JSON object per line.

## 5. Look across many runs

One run tells you little; many runs show patterns.

```sh
tether stats
```

```text
MODEL                                       RUNS  PASS% AVG_STEPS PEAK_TOK TOTAL_TOK NUDGES LOOPS CYCLES SYNTAX_ERR GATE_ERR
nvidia/nvidia/nemotron-3-ultra-550b-a55b       1 100.0%       6.0     1415      5872    0.0   0.0      0        0.0        0
```

Besides the pass rate and token cost, `stats` counts **friction**: how often tether had to nudge a model, break a loop, or answer a malformed command with a usage hint. A model with many `SYNTAX_ERR` needs a clearer task or a simpler toolset. A section below the table lists the commands that caused most of the trouble. `tether misses` lists model replies tether could not parse as ready-made test cases.

## 6. Replay on another model

```sh
tether replay ses_ed3a5a1c --model ollama/qwen3.5:9b
```

Runs the same goal with the same tools and sandbox on another model and prints both runs side by side. It is the quickest way to answer "would the cheap model have done this too?"

## 7. Learn from a bad run

```sh
tether retro ses_ed3a5a1c
```

Reads the friction in a finished session and proposes at most two short rules for a skill, printed as a diff. Nothing changes until you add `--apply`. Tether never rewrites its own instructions in the middle of a run, because that would break the model's cache of the prompt ([why](../../concepts/kv-cache-and-static-prefix.md)).

## When it goes wrong

- **`WAITING_INPUT` after "stuck":** read the summary, refine the task, `tether send <id> "..."`.
- **`FAILED` with a gate error:** your `--verify` command is broken, not the model. Run it by hand.
- **`FAILED` with a worker error:** read `.tether/workers/<id>.log`.

[Troubleshooting](../../troubleshooting.md) lists every message with its cause and fix.
