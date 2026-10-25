# Use tether from Claude Code, Codex or Cursor

*For: people who already work in an agent such as Claude Code, Codex, Cursor or Gemini CLI. After this page you can delegate mechanical tasks to a cheap local model from inside that agent, and know what comes back.*

Your main agent is strong and expensive. Most of what it does in a day is mechanical: fix this failing test, rename that symbol, summarise these files. Tether lets it hand those to a local 9B model and read back **one short answer** instead of a transcript.

## Connect it once

```bash
uv tool install "tether-sdk[mcp]"
claude mcp add tether -- tether mcp --workspace "$PWD"      # Claude Code
codex mcp add tether -- tether mcp --workspace "$PWD"       # Codex CLI
```

Other agents (Cursor, Gemini CLI, VS Code, Claude Desktop) take the same command in their MCP config: see [Use Tether Inside Your Harness](../tutorial/agent-interface.md). `--workspace` fixes the sandbox root, and a caller can only narrow it, never widen it.

## Delegate

Tell the agent when to use it (add this to `CLAUDE.md` or `AGENTS.md`):

```markdown
For mechanical, well-specified tasks (fix failing tests, bulk refactors, summarising files),
call `tether_run` with `model: "ollama/qwen3.5:9b"` and `verify: ["pytest -q"]`.
Use `wait: false` for long jobs, then `tether_wait` and `tether_read`.
If status is `WAITING_INPUT`, answer with `tether_send`. Keep architecture and review for yourself.
```

The agent then calls `tether_run`. What it gets back is a small JSON object, not the model's whole conversation. This is the real answer for a "create `hello.txt`" task with a verification gate (the same JSON you get from `tether run --json` in a shell):

```json
{
  "v": 1,
  "id": "ses_da7f110a",
  "status": "COMPLETED",
  "model": "ollama/qwen3.5:9b",
  "steps": 2,
  "tokens": { "prompt": 837, "completion": 139 },
  "duration_ms": 4597,
  "failure": null,
  "exit_code": 0,
  "result": "hello.txt contains \"hi\""
}
```

About 800 prompt tokens and four seconds, none of them from your main agent's context.

## Without MCP

Any agent that can run a shell command can delegate the same way. The exit code tells it what happened:

```bash
tether run --json --model ollama/qwen3.5:9b --verify "pytest -q" "fix the failing tests"
echo $?    # 0 done, 1 usage error, 2 needs input, 3 gate failed, 4 max steps or stalled, 5 error
```

## Two-way

If the small model needs a decision, it ends with `status: "WAITING_INPUT"` and `result` is its question. The calling agent answers with `tether_send` (or `tether send <id> "..."`), and the session resumes with its context intact. Ask for a typed answer with `output_schema` and `done` is rejected until the deliverable matches it.

## When it goes wrong

- **The agent never calls tether.** Models follow the delegation rule only if it is in their instructions file. Be specific about which tasks.
- **`status: "FAILED"`.** `failure.kind` says why (`gate`, `max_steps`, `worker_error`); read the details with `tether_read` or `tether read <id> --steps`.
- **A task the small model cannot do.** Keep architecture and review in the main agent; delegate only work a gate can check.

Reference: [Agent interface](../reference/agent-interface.md), [CLI](../reference/cli.md).
