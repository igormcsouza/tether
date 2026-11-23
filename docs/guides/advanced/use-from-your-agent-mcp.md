# Use Tether Inside Your Harness

*For: people who already work in Claude Code, Codex, Cursor or another agent. After this page you can delegate tasks to tether from that tool.*

Tether does not ask you to give up your cockpit. Keep Claude Code, Codex, Cursor, Gemini CLI, Copilot or whatever TUI you already use as the main agent, and let Tether run as a **subagent** (or as the main agent for narrow tasks) behind MCP or plain CLI.

Why that is useful:

- **Save tokens.** Hand mechanical work (refactors, test-fixing loops, summarizing docs, scraping) to a cheap or local model. The parent only reads a small structured answer: status, steps, tokens and a digest, never a transcript.
- **Ultra light.** Fixed prompt framing is under 150 tokens and no tools load unless asked, so even a 9B local model has room to think.
- **Any provider.** `ollama/qwen3.5:9b` on your machine, `anthropic/…`, `openai/…` (also OpenRouter, vLLM, Groq via `OPENAI_BASE_URL`). Models from your harness's vendor work too, billed through an API key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`); a subscription login cannot be reused.
- **Safe by default.** Delegated sessions run in the `workspace-write` sandbox, rooted at the directory you give the server, and can only narrow it.

## 1. Install

MCP support is an optional extra, so plain `tether-sdk` stays dependency-light.

```bash
uv tool install "tether-sdk[mcp]"      # or: pip install "tether-sdk[mcp]"
tether mcp --help                       # sanity check
```

No install at all? Use `uvx --from "tether-sdk[mcp]" tether mcp` as the server command in the configs below.

Running `tether mcp` without the extra prints a warning with this install command and exits 1.

## 2. Register the server in your harness

The server speaks MCP over stdio. Pass `--workspace` so the sandbox root does not depend on how the harness launches it. Use an absolute path, or the harness's project-scoped config.

=== "Claude Code"

    ```bash
    claude mcp add tether -- tether mcp --workspace "$PWD"
    # share with the team via .mcp.json:
    claude mcp add --scope project tether -- tether mcp --workspace "$PWD"
    ```

=== "Codex CLI"

    ```bash
    codex mcp add tether -- tether mcp --workspace "$PWD"
    ```

    or in `~/.codex/config.toml`:

    ```toml
    [mcp_servers.tether]
    command = "tether"
    args = ["mcp", "--workspace", "/abs/path/to/project"]
    ```

=== "Gemini CLI"

    `~/.gemini/settings.json` (or `.gemini/settings.json` in the project):

    ```json
    { "mcpServers": { "tether": { "command": "tether", "args": ["mcp", "--workspace", "/abs/path/to/project"] } } }
    ```

=== "Cursor"

    `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

    ```json
    { "mcpServers": { "tether": { "command": "tether", "args": ["mcp", "--workspace", "/abs/path/to/project"] } } }
    ```

=== "VS Code (Copilot)"

    `.vscode/mcp.json`:

    ```json
    { "servers": { "tether": { "type": "stdio", "command": "tether", "args": ["mcp", "--workspace", "${workspaceFolder}"] } } }
    ```

=== "Claude Desktop"

    `claude_desktop_config.json`, then restart the app:

    ```json
    { "mcpServers": { "tether": { "command": "tether", "args": ["mcp", "--workspace", "/abs/path/to/project"] } } }
    ```

=== "Any other MCP client"

    Command `tether`, args `mcp --workspace <dir>`, transport stdio. If the client cannot find `tether`, use the absolute path from `which tether`. Harnesses without MCP can call the CLI instead (see [Without MCP](#without-mcp)).

Config formats change between harness releases; if one of the snippets is rejected, check your harness's MCP docs. The command and arguments stay the same.

## 3. Or let your harness do it

Paste this into your harness and let it install and configure Tether for you:

> Install Tether as an MCP server for yourself. Run `uv tool install "tether-sdk[mcp]"` (or `pip install "tether-sdk[mcp]"` if `uv` is missing), then register it with your own MCP configuration as a stdio server with command `tether` and args `mcp --workspace <this project's absolute path>`. Then call `tether_list` to confirm it works, and tell me whether I need to restart you.

## 4. Tell the parent when to delegate

Add a short rule to `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` or your Cursor rules:

```markdown
## Delegating to Tether
For mechanical, well-specified tasks (fix failing tests, bulk refactors, summarizing files),
call `tether_run` with `model: "ollama/qwen3.5:9b"` and `verify: ["pytest -q"]`.
Use `wait: false` for long jobs, then `tether_wait` and `tether_read`.
If status is `WAITING_INPUT`, answer with `tether_send`. Keep architecture and review for yourself.
```

## Any model, no code: providers.yaml

Delegate to any backend you declare in `~/.tether/providers.yaml` (a gateway, a remote Ollama, a `claude -p` style command). Location, worked examples and every setting are on one page: [Model providers](../../reference/providers.md).

## Patterns

**Architect / executor.** The frontier model writes the spec and the tests. `tether_run` with `verify: ["pytest -q"]` implements it with a cheap model; the gate runs in the sandbox before `done` is accepted. The parent reads back only status, steps, tokens and the digest.

**Two-way protocol.** `status: "WAITING_INPUT"` means `result` is the agent's question. Answer with `tether_send` (`wait: true` blocks for the outcome).

**Typed results.** Pass `output_schema` (or `--output-schema`) and `done` is rejected until the deliverable is valid JSON matching the schema.

**Tether as the main agent.** For narrow, repeatable jobs, skip the parent: `tether run --skill researcher "…"` straight from your shell or CI.

## Without MCP

Every MCP tool has a CLI twin with the same JSON, so any harness that can run a shell command can delegate:

```bash
tether run --json --model ollama/qwen3.5:9b --verify "pytest -q" "fix the failing tests"
echo $?   # 0 ok, 2 needs input, 3 gate failed, 5 error
```

See the [reference](../../reference/agent-interface.md) for the JSON shape, exit codes and all tools.

## What comes back

The agent gets a small JSON object, never the other model's transcript. This is a real one (the same object `tether run --json` prints):

```json
{
  "v": 1,
  "id": "ses_09a5d090",
  "status": "COMPLETED",
  "model": "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
  "steps": 3,
  "tokens": { "prompt": 1845, "completion": 748 },
  "duration_ms": 13569,
  "failure": null,
  "exit_code": 0
}
```

plus a `result` field with the answer. Exit codes: `0` done, `2` waiting or stuck, `3` your check failed, `5` worker error.

## Why it works this way

- **A subagent, not a replacement.** Your harness stays the place where you work; tether takes the mechanical jobs and returns a small structured answer, so the parent spends tokens on judgement.
- **The result is JSON with an exit code.** Any agent, script or CI job can use it without parsing prose.
- **The server is rooted in one folder and can only narrow it.** A delegated session cannot be talked into touching more than `--workspace` allows.
- **MCP is an optional extra.** Plain `tether-sdk` stays small, and the official `mcp` package is imported only when you start the server.

## When it goes wrong

- **`MCP support is not installed`.** `pip install "tether-sdk[mcp]"`.
- **The agent never calls tether.** Put the delegation rule in its instructions file ([delegate from your agent](delegate-from-your-agent.md)).
- **A call from the agent is refused.** A caller cannot widen the sandbox (`allow`, `allow_unsandboxed`) unless the server was started with `--permit-widen`.

See also [Troubleshooting](../../troubleshooting.md).
