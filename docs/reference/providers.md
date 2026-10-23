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

Every entry, of any kind, may set optional positive integers: `context_tokens` (the context budget, default 8192), `fold_after` (how many recent turns keep full observations, default 2) and, for HTTP kinds (`openai`, `ollama`, `anthropic`), `rpm` (maximum requests per minute, off by default; a sliding window shared by every tether process on the machine through a lock file in `$TMPDIR`, or `TETHER_RATE_DIR`). The `--context-tokens` / `--fold-after` flags and the Harness arguments override the first two.

### Timeout and retry

Every entry may set `timeout` (positive seconds). It applies to the HTTP kinds (`openai`, `ollama`, `anthropic`; defaults 120 / 120 / 180 s) and to `command` (default 300 s). The HTTP providers retry automatically, at most 2 times with 1 s then 2 s backoff, on timeouts, network errors and HTTP 429/500/502/503/504. A 401/403 is never retried: it raises `ProviderError` naming the provider and the credential variable (`openai: HTTP 401: `NVIDIA_API_KEY` is missing or rejected; set it to a valid key`; the value is never printed), and a declared `api_key_env` that is unset or empty fails the session before any request with the same message. Other 4xx responses are never retried. When retries run out the call raises `ProviderError`, so the session fails with a readable `Worker error: ProviderError: openai model `gpt-4o` unavailable after 3 attempts (timeout 120s, last error: ReadTimeout)`. The retry is invisible to the prompt (0 tokens, no prefix change).

### Kinds

| `kind` | Fields |
|---|---|
| `openai` | `base_url`, `api_key_env`, optional `timeout` |
| `ollama` | `host`, optional `timeout` |
| `anthropic` | `base_url`, `api_key_env`, optional `timeout` |
| `command` | `argv` (list), `reply` (JSON path), optional `stdin` template, optional `usage`, optional `timeout` (seconds, default 300) |

`api_key_env` is the **name** of an environment variable, never the key itself. A declared `api_key_env` must be set and non-empty (otherwise the session fails before any request); omit it to declare a keyless local server. A 403 reads `access denied (HTTP 403)` with the first 120 characters of the response body instead of "missing or rejected".

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

## NVIDIA free tier

One `nvidia:` entry (above, with `rpm: 36` for the 40 requests/min cap) serves every model on `integrate.api.nvidia.com`; the model is whatever follows the prefix, e.g. `--model nvidia/nvidia/nemotron-3-ultra-550b-a55b`. Checked with one chat request on a free key (2026-10-23); availability changes per account, so a `404 Function ... Not found for account` means the model is not enabled for your key:

| Model | Id after `nvidia/` | Status |
|---|---|---|
| Nemotron 3 Ultra | `nvidia/nemotron-3-ultra-550b-a55b` | works |
| Kimi K2.6 | `moonshotai/kimi-k2.6` | listed, 404 for the checked account |
| GLM-5.2 | `z-ai/glm-5.2` | end of life (410); use `z-ai/glm-5.3` |
| Mistral Large 3 | `mistralai/mistral-large-3-675b-instruct-2512` | gone (410); `mistralai/mistral-large*` 404 |

## Request parameters (`params`)

HTTP kinds (`openai`, `ollama`, `anthropic`) accept `params`, merged into the request body over the adapter's defaults (temperature 0.2). For `ollama`, `think`, `keep_alive`, `format` and `stream` are request-level keys and everything else (`temperature`, `top_p`, ...) goes into `options`.

```yaml
nvidia:
  kind: openai
  base_url: https://integrate.api.nvidia.com/v1
  api_key_env: NVIDIA_API_KEY
  params: {temperature: 0, reasoning_effort: low}
```

The yaml values are defaults; a call overrides them key by key:

| Surface | How |
|---|---|
| CLI | `tether run --param temperature=0.7 --param think=false "goal"` (repeatable, JSON values) |
| SDK | `Harness(model=..., params={"temperature": 0.7})` |
| MCP | `tether_run` with `params: {"temperature": 0.7}` |

Params are stored with the session, so `send` and a resumed worker keep using them. Precedence: call > `providers.yaml` > adapter default. Not supported for `kind: command` (put flags in `argv`).
