# Model Providers

## Structured history

The harness passes neutral messages (assistant `tool_calls` with `id` and dict `arguments`, then `{"role": "tool", "tool_call_id": ...}`) to providers whose `structured_history` attribute is true, and each adapter translates: Ollama sends them as-is (plus `tool_name`), OpenAI-compatible JSON-encodes `arguments`, Anthropic maps them to `tool_use` and `tool_result` blocks (merging consecutive same-role messages). A custom provider without the attribute gets the textual `act('...')` / `Observation:` form. Adapter payloads are unit-tested with mock transports; they have not been verified live against OpenAI or Anthropic.

## `tether.providers`

::: tether.providers
    options:
      show_root_heading: false
      members_order: source

## `tether.providers.base`

::: tether.providers.base
    options:
      show_root_heading: false
      members_order: source

Ollama: an unknown model fails with `Ollama model … not found; installed: …`. Set `TETHER_OLLAMA_FALLBACK=1` (or `OllamaProvider(fallback=True)`) to substitute an installed model instead; a warning is printed to stderr and `tether stats` records the substitute ([#21](https://github.com/igormcsouza/tether/issues/21)).

## Declarative providers

Add providers without writing code by declaring them in `~/.tether/providers.yaml` (override the path with the `TETHER_PROVIDERS` environment variable). The file is read only from the home directory (or `TETHER_PROVIDERS`), never from the workspace, so a cloned repo cannot plant a provider.

The entry key is the model-id prefix: `claude-cli/sonnet` uses the entry named `claude-cli`, and `sonnet` is passed on as the model name. Declared providers work in `tether run`, `tether pipeline`, the Python SDK and `tether mcp`.

```yaml
claude-cli:
  kind: command
  argv: [claude, -p, --model, "{model}", --tools, "", --system-prompt, "{system}", --output-format, json, --no-session-persistence, --setting-sources, "", --disable-slash-commands, --strict-mcp-config]
  stdin: "{conversation}"
  reply: result
  usage: {prompt: [usage.input_tokens, usage.cache_creation_input_tokens, usage.cache_read_input_tokens], completion: usage.output_tokens}
  timeout: 180
  context_tokens: 32000
  fold_after: 8
```

```bash
tether run --model claude-cli/sonnet "fix the failing test"
```

### Context budget

Every entry, of any kind, may set two optional positive integers: `context_tokens` (the context budget, default 8192) and `fold_after` (how many recent turns keep full observations, default 2). The `--context-tokens` / `--fold-after` flags and the Harness arguments override them.

### Kinds

| `kind` | Fields |
|---|---|
| `openai` | `base_url`, `api_key_env` |
| `ollama` | `host` |
| `anthropic` | `base_url`, `api_key_env` |
| `command` | `argv` (list), `reply` (JSON path), optional `stdin` template, optional `usage`, optional `timeout` (seconds, default 300) |

`api_key_env` is the **name** of an environment variable, never the key itself.

### The `command` kind

A `command` entry wraps any program that takes a prompt and prints JSON.

- **Placeholders**: `{model}`, `{system}`, `{conversation}` and `{schema}` (the act JSON schema, compact) are substituted in `argv` items and in the `stdin` template. If `stdin` is omitted it defaults to `{conversation}`.
- **No shell**: `argv` is executed directly, never through a shell.
- **Reply**: `reply` is a dotted path into the JSON the command prints (`result` in the example).
- **Usage**: `usage.prompt` is a path or a list of paths (their values are summed); `usage.completion` is a path. Both are optional.
- **Constrained output**: use `{schema}` to make the CLI constrain its reply to the act schema, for example `argv: [claude, -p, --json-schema, "{schema}", --output-format, json]`. The reply may then be an object with `cmd` and optional `stdin` instead of a string; if the `reply` path gives no string or object, a top-level `structured_output` object is used.

  Measured cost (v0.2.2, one small task): with `claude -p`, `--json-schema` adds about 2k prompt tokens to every call (the CLI wraps the schema in a hidden tool), so the same 5-step task used ~26k prompt tokens instead of ~7k. Use it when a model's plain replies are not being understood, not as a default.
- **Protocol**: the model should answer with a single JSON `{"cmd", "stdin"}` object. The `{system}` placeholder already contains that instruction.
- **Dialects**: when the reply is not that JSON, Tether tries table-driven extractors in order, first match wins: `<tool_call>` JSON, raw JSON containing `"cmd"`, `<parameter name="cmd">X</parameter>` with optional `<parameter name="stdin">Y</parameter>` (inside any wrapper such as `<invoke>`), and text `act(...)`.
- **`dialects:`** (optional): a list of mappings, each with a `regex` (compiled with `re.DOTALL`) that defines the named group `cmd` and optionally `stdin`. Custom dialects are tried after the built-in ones. Python users can also call `tether.register_dialect(fn)` with a `(str) -> ActionCall | None` function.

```yaml
mycli:
  kind: command
  argv: [mycli, "{conversation}"]
  reply: result
  dialects:
    - regex: 'RUN\[(?P<cmd>.*?)\]WITH\[(?P<stdin>.*?)\]'
```

### Rules

- The built-in prefixes `ollama`, `openai`, `anthropic` and `claude` cannot be shadowed.
- An invalid file raises `ValueError: providers.yaml: ...` naming the offending entry.

### Measured example

On one small bug-fix task (v0.2.0 test), using `claude -p --tools ""` as the backend, as in the entry above, used about 15x fewer tokens than plain `claude -p` (21k vs 330k). This is a single small task, not a benchmark.

## `tether.providers.ollama`

::: tether.providers.ollama
    options:
      show_root_heading: false
      members_order: source

## `tether.providers.openai`

::: tether.providers.openai
    options:
      show_root_heading: false
      members_order: source

## `tether.providers.anthropic`

::: tether.providers.anthropic
    options:
      show_root_heading: false
      members_order: source

## `tether.providers.declarative`

::: tether.providers.declarative
    options:
      show_root_heading: false
      members_order: source
