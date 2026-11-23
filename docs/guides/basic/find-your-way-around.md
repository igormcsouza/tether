# Find your way around

*For: anyone who just installed tether. After this page you know where tether keeps its files, how to check that your setup works, and which command to use for what.*

Tether has no daemon and no cloud account. It is a command, a folder per project, and one optional file in your home directory.

## Where things live

| What | Where | Why there |
|---|---|---|
| Sessions, turns, full tool outputs, notes | `.tether/tether.db` in the folder where you run tether | One database per project. Its history belongs to that project and goes away with it. Change it with `--db` or `TETHER_DB`. |
| Provider settings | `~/.tether/providers.yaml` | One file for all projects. Tether never reads it from a project folder, so a repository you cloned cannot add a provider. Use `TETHER_PROVIDERS` for another path. |
| Skills | `./skills/` in the project and `~/.tether/skills/` | Project skills travel with the repository, personal skills with you. |
| Commands you allowed outside the sandbox | `.tether/allow.json` | Per project, so an approval for one repository does not leak into another. |
| Logs of a background worker | `.tether/workers/<session id>.log` | Where to look when a detached run died before it started. |

Add `.tether/` to your `.gitignore`. Tether keeps its own folder out of the sandbox as well: a model cannot read or change it.

## Check the setup

```sh
tether doctor
```

```text
FAIL ollama  cannot reach Ollama at http://localhost:11434 ([Errno 111] Connection refused); start Ollama or set OLLAMA_HOST
FAIL model  cannot check: Ollama is not reachable
ok   bwrap  /usr/bin/bwrap
ok   providers  5 declared
ok   db  .tether/tether.db
```

That is a real run on a machine where Ollama listens on another port. Every line says either `ok` or what to do. In this case:

```sh
OLLAMA_HOST=http://localhost:11435 tether doctor
```

`bwrap` is the Linux jail that keeps commands inside your project folder. If it is missing, or the kernel blocks it, `doctor` says which, and tether refuses to let a model write files until you fix it or opt out on purpose (see [Security and sandbox](../advanced/security-and-sandbox.md)).

## The commands you will use

| Command | What it does |
|---|---|
| `tether "goal"` or `tether run "goal"` | Run a task and print the result |
| `tether run --headless "goal"` | Run it in the background and print the session id |
| `tether list` | Your recent sessions |
| `tether status <id>` | Where a session is right now |
| `tether read <id>` | The final answer (`--steps` for every step) |
| `tether send <id> "..."` | Answer a question or give a follow-up |
| `tether stats` | Pass rate, steps, tokens and friction per model |
| `tether diff <id>` | The files a session changed |
| `tether doctor` | Check the setup |

Every command is explained with all its flags in the [CLI reference](../../reference/cli.md).

## What a session is

Every run is a **session**: a row in the database with its goal, model, tools, every step and every full output. A session ends in one of three states:

- `COMPLETED`: the model called `done`, or your `--verify` check passed.
- `FAILED`: something broke (a provider outage, a check that is misconfigured). The message says what.
- `WAITING_INPUT`: the model asked you a question, ran out of steps, or got stuck. This is not a failure. The work so far is kept, and `tether send <id> "..."` continues it.

Because the database keeps everything, you can come back to a session tomorrow, search it, export it or replay it on another model. [Review and debug a session](review-and-debug.md) shows how.
