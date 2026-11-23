# tether

*For: anyone deciding whether to use tether, and agents looking for the right page. After this page you can install tether, run your first task and see where to go next.*

**Tether is a small harness that lets a small model do real work.** You give it a goal in plain words. It lets a model (a 9B model on your own laptop, or Claude, GPT, Nemotron) run commands, read and write files, search the web and check its own work, then hands you the result.

Most agent tools were built for giant models and cost 3,000 to 8,000 tokens of tool descriptions before the model says a word. A small model drowns in that. Tether keeps its fixed instructions under 150 tokens, loads no tools you did not ask for, and keeps the model's working memory short, so a model that fits on your graphics card has room left to think.

That gives you three things:

- **Cheap and private.** Routine work runs on a local model. Nothing leaves your machine unless you point tether at a hosted model.
- **Safe by default.** Every command runs in a jail that can only touch your project folder. The safety does not depend on the model behaving.
- **Checked, not trusted.** You can give tether a command (`--verify "pytest"`) and it will not accept "done" until that command passes.

## Install

Tether needs Python 3.12 or newer.

=== "uv tool (recommended)"

    ```sh
    uv tool install tether-sdk
    ```

=== "pip"

    ```sh
    pip install tether-sdk
    ```

=== "no install"

    ```sh
    uvx --from tether-sdk tether "Explain the CAP theorem in 3 bullet points"
    ```

By default tether talks to [Ollama](https://ollama.com) on your machine and uses the model `qwen3.5:9b`. If you do not have it yet:

```sh
ollama pull qwen3.5:9b
tether doctor        # checks Ollama, the model, the sandbox and your config, and says what to fix
```

## Your first call

```sh
tether "Explain the CAP theorem in 3 bullet points"
```

This is the real output, from an 8 GB laptop GPU, in 38 seconds (most of it loading the model for the first time):

```text
CAP Theorem in 3 bullet points:

1. In a distributed system, you can only guarantee 2 out of 3 properties simultaneously: Consistency, Availability, and Partition Tolerance.

2. The three properties are: Consistency (all nodes see same data), Availability (every request gets a response), and Partition Tolerance (system works despite network partitions).

3. When a network partition occurs, systems must choose between Consistency (CP) or Availability (AP), making this a fundamental trade-off in distributed system design.
```

The answer goes to your terminal and the session is stored, so you can look at what happened:

```sh
tether list          # every session, newest first
tether stats         # pass rate, steps and tokens per model
```

```text
ID             STATUS    MODEL                  STEP    GOAL
ses_d065a28e   COMPLETED ollama/qwen3.5:9b      1/15   Explain the CAP theorem in 3 bullet points
```

One step and 809 tokens in total. No tools were loaded, because this task needed none.

## What tether can do for you

These short pages each end with something you can run now:

| | |
|---|---|
| [Search the web and write a summary](start/search-and-summarize.md) | A local model reads real pages and cites its sources. |
| [Let Claude call tether to review your writing](start/review-with-claude.md) | Keep Claude as your editor and send the mechanical reading to a cheaper model. |
| [Write and check a script with Nemotron](start/script-with-nemotron.md) | A big free hosted model writes the code, and a check command decides when it is done. |

After that, the [Guides](guides/index.md) cover everything else tether can do, from your first provider file to pipelines and sandboxes. If something does not work, start with [Troubleshooting](troubleshooting.md).

## How it compares

| | Typical agent framework | Tether |
|---|---|---|
| Fixed prompt before the first step | 3,000 to 8,000+ tokens | under 150 tokens |
| Tools loaded by default | 15 to 30 | none (only `done`) |
| Long outputs | pile up in the prompt | folded to one line, kept in SQLite, searchable |
| Safety | "please do not touch `.env`" in the prompt | an operating-system jail, enforced outside the model |
| Sub-agents | the child's whole transcript lands in the parent | a 50-token digest, details on demand |

Why these choices work is explained in [Concepts](concepts/index.md), and the numbers behind them are in [Benchmarks](benchmarks/index.md).

For agents: [`llms.txt`](llms.txt) lists every page with a one-line description.
