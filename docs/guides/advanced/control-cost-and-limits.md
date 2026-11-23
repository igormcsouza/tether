# Control cost and limits

*For: people running tether on paid models, long jobs or shared machines. After this page you can cap steps, tokens, time and machine resources, and choose what the model sees.*

A model that works for you can also work too long. Tether has a separate limit for each thing that can run away, and every limit ends the same way: the session stops cleanly as `WAITING_INPUT` with a summary, your work is kept, and `tether send <id> "..."` continues it.

## Steps

```sh
tether run --max-steps 15 "..."
```

A step is one model turn. The default is generous; a small number is a good fit for a narrow task and keeps a confused model from burning time. When the steps run out, tether asks the model once for its final answer, so you get what it knows instead of an empty hand-back. `send` grants a fresh budget but never lets the count pass the new ceiling.

## Tokens

```sh
tether run --max-tokens 200000 --model anthropic/claude-3-7-sonnet-latest "..."
```

The budget counts prompt plus completion tokens and is checked after every step. When it is reached the session pauses with:

```text
[TOKEN BUDGET] used 201344 of 200000 tokens
```

`send` grants the same amount again. This is the guard to put on any hosted model you pay for.

## Time

A check command (`--verify`) has its own timeout, 300 seconds by default, so a slow test suite is not killed as if it were a stuck command. Change it with `TETHER_GATE_TIMEOUT=900`. Each model request has a timeout set per provider (`timeout:` in [providers.yaml](../basic/configure-providers.md)); timeouts and rate limits retry twice before the run fails with a message that names the provider.

Ctrl+C stops a foreground run cleanly: one line, exit code `130`, the session handed back and any running command killed.

## What the model sees

| Setting | What it does | When to change it |
|---|---|---|
| `--context-tokens N` | Size of the window (default 32,768) | Raise it only if the model stays fully on your GPU at that size. A window that spills into system memory slows every step. |
| `--fold-after N` | Fold outputs older than N turns | Rarely. The default folds only as needed ([why](../../concepts/context-and-folding.md)). |
| `--max-steps`, `--max-tokens` | See above | Always on hosted models |

On a paid model a smaller window is usually cheaper, because you are billed for the prompt every step. On a local model use the largest window that fits, because tokens are free and re-reading files is slow.

## Machine resources

```sh
tether run --tools bash --limit cpu=60 --limit mem=1024 --limit procs=50 --limit fsize=100 "..."
```

Per command: CPU seconds, memory in MB, number of processes, file size in MB. Off by default and Linux only. When a command hits a limit, the model sees one labelled line saying which, and what to do instead.

## Network and files

```sh
tether run --tools web --web-allow "python.org,*.github.com" "..."   # only these hosts
tether run --tools bash --no-network "..."                           # no network at all inside bash
tether run --sandbox read-only "..."                                 # no writes anywhere
```

More in [Security and sandbox](security-and-sandbox.md).

## Typed answers

```sh
tether run --output-schema invoice.schema.json --result-file out.json "Extract the invoice in email.txt"
```

`done` is refused until the answer validates against your JSON Schema, so a script can trust the shape of the result. `--result-file` writes the answer to a file instead of the terminal.

## Putting it together

For an unattended job on a paid model:

```sh
tether run --headless --model anthropic/claude-3-7-sonnet-latest \
  --max-steps 30 --max-tokens 300000 --verify "pytest -q" \
  "Fix the failing tests in tests/test_billing.py"
```

You get a session id back at once. Come back later with `tether wait <id>` and `tether read <id>`. If it was stopped for budget, read the summary and decide whether the extra tokens are worth it.
