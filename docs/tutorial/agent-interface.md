# Calling Tether from Another Agent

Use Tether as a cheap/local subagent for Claude Code, Cursor or any MCP client. The caller sends a goal, gets a small structured answer, and never reads a transcript.

## Claude Code

Install the optional MCP extra (plain `tether-sdk` works without it):

```bash
pip install "tether-sdk[mcp]"
claude mcp add tether -- tether mcp --workspace "$PWD"
```

Then ask Claude to delegate: *"use tether_run with model ollama/qwen3.5:9b to implement X, verify with `pytest -q`"*. For long tasks pass `wait: false`, then call `tether_wait` and `tether_read`.

## Two-way protocol

If the result has `status: "WAITING_INPUT"`, `result` is the agent's question. Answer with `tether_send` (`wait: true` to block for the outcome).

## Architect / executor

1. A frontier model writes the spec and tests.
2. `tether_run` with `verify: ["pytest -q"]` and a cheap model implements it. The gate runs inside the sandbox before `done` is accepted.
3. The parent reads back only `status`, `steps`, `tokens` and a digest.

## Scripts

```bash
tether run --json --model ollama/qwen3.5:9b --output-schema out.json "extract the items"
echo $?   # 0 ok, 2 needs input, 3 gate failed, 4 max steps, 5 error
```

See the [reference](../reference/agent-interface.md) for the JSON shape, exit codes and all tools.
