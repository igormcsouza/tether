# Use Tether Inside Your Harness

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

Tether can route to any backend you declare in `~/.tether/providers.yaml` (override the path with `TETHER_PROVIDERS`). The entry key is the model-id prefix, so `claude-cli/sonnet` uses the entry `claude-cli`. It works the same in `tether run`, `tether pipeline`, the SDK and `tether mcp`, and it is never read from the workspace.

The `command` kind wraps any program that reads a prompt and prints JSON, for example a `claude -p`, `codex exec` or `gemini -p` style command (check each tool's own docs for its flags). Tether runs `argv` directly, never through a shell.

```yaml
claude-cli:
  kind: command
  argv: [claude, -p, --model, "{model}", --tools, "", --system-prompt, "{system}", --output-format, json, --no-session-persistence, --setting-sources, "", --disable-slash-commands, --strict-mcp-config]
  stdin: "{conversation}"
  reply: result
  usage: {prompt: [usage.input_tokens, usage.cache_creation_input_tokens, usage.cache_read_input_tokens], completion: usage.output_tokens}
  timeout: 180
```

```bash
tether run --model claude-cli/sonnet "fix the failing test"
```

On one small bug-fix task, this backend used about 15x fewer tokens than plain `claude -p` (21k vs 330k). It is a single small task, not a benchmark. Full reference: [Declarative providers](../reference/providers.md#declarative-providers).

## Patterns

**Architect / executor.** The frontier model writes the spec and the tests. `tether_run` with `verify: ["pytest -q"]` implements it with a cheap model; the gate runs in the sandbox before `done` is accepted. The parent reads back only status, steps, tokens and the digest.

**Two-way protocol.** `status: "WAITING_INPUT"` means `result` is the agent's question. Answer with `tether_send` (`wait: true` blocks for the outcome).

**Typed results.** Pass `output_schema` (or `--output-schema`) and `done` is rejected until the deliverable is valid JSON matching the schema.

**Tether as the main agent.** For narrow, repeatable jobs, skip the parent: `tether run --skill researcher "…"` straight from your shell or CI.

## Without MCP

Every MCP tool has a CLI twin with the same JSON, so any harness that can run a shell command can delegate:

```bash
tether run --json --model ollama/qwen3.5:9b --verify "pytest -q" "fix the failing tests"
echo $?   # 0 ok, 2 needs input, 3 gate failed, 4 max steps, 5 error
```

See the [reference](../reference/agent-interface.md) for the JSON shape, exit codes and all tools.
