# Model providers

Tether reaches a model through its **prefix**: `ollama/qwen3.5:9b`, `openai/gpt-4o-mini`, `anthropic/claude-sonnet-5-5`. The prefix picks the provider, the rest is passed on as the model name. Three prefixes are built in; you can add your own without writing code.

| Prefix | Talks to | Environment |
|---|---|---|
| `ollama/<model>` | Ollama `/api/chat` | `OLLAMA_HOST` (default `http://localhost:11434`) |
| `openai/<model>` | any OpenAI-compatible server (OpenAI, OpenRouter, vLLM, llama.cpp, Groq) | `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) |
| `anthropic/<model>` | Anthropic `/v1/messages` | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` (default `https://api.anthropic.com`) |

## Add your own with providers.yaml

Declare a provider in `~/.tether/providers.yaml`; set `TETHER_PROVIDERS` to use another path. The file is **never read from the workspace**, so a cloned repository cannot plant a provider. The entry key is the model-id prefix: `my-gateway/some-model` uses the entry `my-gateway`, and `some-model` is passed on as the model name. Declared providers work in `tether run`, `tether pipeline`, the Python SDK and `tether mcp`.

One generic entry per kind:

```yaml
my-gateway:            # kind: openai - any OpenAI-compatible server
  kind: openai
  base_url: https://llm.example.com/v1
  api_key_env: MY_GATEWAY_KEY

my-gpu-box:            # kind: ollama - an Ollama on another machine
  kind: ollama
  host: http://gpu-box:11434

my-claude:             # kind: anthropic - Anthropic or a compatible proxy
  kind: anthropic
  base_url: https://api.anthropic.com
  api_key_env: MY_ANTHROPIC_KEY
```

```yaml
my-cli:                # kind: command - wrap a program that takes a prompt and prints JSON
  kind: command
  argv: [my-cli, --model, "{model}", --system-prompt, "{system}", --output-format, json]
  stdin: "{conversation}"
  reply: result        # dotted path into the JSON the program prints
```

`api_key_env` is the **name** of an environment variable, never the key itself. A declared `api_key_env` must be set and non-empty (otherwise the session fails before any request); omit it to declare a keyless local server. A 403 reads `access denied (HTTP 403)` with the first 120 characters of the response body instead of "missing or rejected".


| `kind` | Fields |
|---|---|
| `openai` | `base_url`, `api_key_env`, optional `timeout` |
| `ollama` | `host`, optional `timeout` |
| `anthropic` | `base_url`, `api_key_env`, optional `timeout` |
| `command` | `argv` (list), `reply` (JSON path), optional `stdin` template, optional `usage`, optional `timeout` (seconds, default 300) |

- The built-in prefixes `ollama`, `openai`, `anthropic` and `claude` cannot be shadowed.
- An invalid file raises `ValueError: providers.yaml: ...` naming the offending entry.

## Verify it works

```bash
tether run --model my-gateway/some-model "reply with the word ok"
```

If it fails, the message says why: `providers.yaml: ...` names the invalid entry; a 401/403 names the `api_key_env` variable that is missing or rejected (the value is never printed); an unset `api_key_env` fails the session before any request is sent.

## Add your own in Python

For a transport that is not HTTP-with-YAML (an internal SDK, a replay harness in tests), implement `generate` and register it under a prefix, or hand the object straight to a `Harness`:

```python
from tether import Harness, ModelResponse, extract_fallback_action, register_provider


class MyGatewayProvider:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def generate(self, messages: list[dict], tools: list[dict]) -> ModelResponse:
        text = 'act("done", stdin="hello from my gateway")'  # call your backend here
        return ModelResponse(content=text, action=extract_fallback_action(text), prompt_tokens=128)


register_provider("my-gateway", MyGatewayProvider)  # then: model="my-gateway/anything"
harness = Harness(model="my-gateway/anything")
harness = Harness(provider=MyGatewayProvider("anything"))  # or inject it directly
```

## Entry settings

Any entry may add these optional keys.

### Context budget

Every entry, of any kind, may set optional positive integers: `context_tokens` (the context budget, default 8192), `fold_after` (how many recent turns keep full observations, default 2) and, for HTTP kinds (`openai`, `ollama`, `anthropic`), `rpm` (maximum requests per minute, off by default; a sliding window shared by every tether process on the machine through a lock file in `$TMPDIR`, or `TETHER_RATE_DIR`). The `--context-tokens` / `--fold-after` flags and the Harness arguments override the first two.


### Timeout and retry

Every entry may set `timeout` (positive seconds). It applies to the HTTP kinds (`openai`, `ollama`, `anthropic`; defaults 120 / 300 / 180 s) and to `command` (default 300 s). The HTTP providers retry automatically, at most 2 times with 1 s then 2 s backoff, on timeouts, network errors and HTTP 429/500/502/503/504. A 401/403 is never retried: it raises `ProviderError` naming the provider and the credential variable (`openai: HTTP 401: `MY_GATEWAY_KEY` is missing or rejected; set it to a valid key`; the value is never printed), and a declared `api_key_env` that is unset or empty fails the session before any request with the same message. Other 4xx responses are never retried. An HTTP 500 whose body names a rejected tool call (Ollama: `invalid tool call arguments`, a cut-off tool-call JSON) is not retried either, since the same request fails the same way; `ollama`, `openai` and `anthropic` turn it into a one-line hint to the model (a no-action reply), so the session continues instead of failing. The match is the text `tool call` in a 500 body, for any server. When retries run out the call raises `ProviderError`, so the session fails with a readable `Worker error: ProviderError: openai model `gpt-4o` unavailable after 3 attempts (timeout 120s, last error: ReadTimeout)`. When they run out the harness waits 10 s (set `TETHER_OUTAGE_BACKOFF`) and tries the whole call again, up to 3 more times with doubling waits, before the session fails. The retry is invisible to the prompt (0 tokens, no prefix change).


### Request parameters (`params`)

HTTP kinds (`openai`, `ollama`, `anthropic`) accept `params`, merged into the request body over the adapter's defaults (temperature 0.2). For `ollama`, `think`, `keep_alive`, `format` and `stream` are request-level keys and everything else (`temperature`, `top_p`, ...) goes into `options`.

```yaml
my-gateway:
  kind: openai
  base_url: https://llm.example.com/v1
  api_key_env: MY_GATEWAY_KEY
  params: {temperature: 0, reasoning_effort: low}
```

The yaml values are defaults; a call overrides them key by key:

| Surface | How |
|---|---|
| CLI | `tether run --param temperature=0.7 --param think=false "goal"` (repeatable, JSON values) |
| SDK | `Harness(model=..., params={"temperature": 0.7})` |
| MCP | `tether_run` with `params: {"temperature": 0.7}` |

Params are stored with the session, so `send` and a resumed worker keep using them. Precedence: call > `providers.yaml` > adapter default. Not supported for `kind: command` (put flags in `argv`).

## The `command` kind

A `command` entry wraps any program that takes a prompt and prints JSON.

- **Placeholders**: `{model}`, `{system}`, `{conversation}` and `{schema}` (the act JSON schema, compact) are substituted in `argv` items and in the `stdin` template. If `stdin` is omitted it defaults to `{conversation}`.
- **No shell**: `argv` is executed directly, never through a shell.
- **Reply**: `reply` is a dotted path into the JSON the command prints (`result` in the example).
- **Usage**: `usage.prompt` is a path or a list of paths (their values are summed); `usage.completion` is a path. Both are optional.
- **Constrained output**: use `{schema}` to make the CLI constrain its reply to the act schema, for example `argv: [claude, -p, --json-schema, "{schema}", --output-format, json]`. The reply may then be an object with `cmd` and optional `stdin` instead of a string; if the `reply` path gives no string or object, a top-level `structured_output` object is used.

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

## Python API

### Structured history

The harness passes neutral messages (assistant `tool_calls` with `id` and dict `arguments`, then `{"role": "tool", "tool_call_id": ...}`) to providers whose `structured_history` attribute is true, and each adapter translates: Ollama sends them as-is (plus `tool_name`), OpenAI-compatible JSON-encodes `arguments`, Anthropic maps them to `tool_use` and `tool_result` blocks (merging consecutive same-role messages). A custom provider without the attribute gets the textual `act('...')` / `Observation:` form. Adapter payloads are unit-tested with mock transports; they have not been verified live against OpenAI or Anthropic.

### `tether.providers`

::: tether.providers
    options:
      show_root_heading: false
      members_order: source

### `tether.providers.base`

::: tether.providers.base
    options:
      show_root_heading: false
      members_order: source


Ollama: an unknown model fails with `Ollama model … not found; installed: …`. Set `TETHER_OLLAMA_FALLBACK=1` (or `OllamaProvider(fallback=True)`) to substitute an installed model instead; a warning is printed to stderr and `tether stats` records the substitute.

### `tether.providers.ollama`

::: tether.providers.ollama
    options:
      show_root_heading: false
      members_order: source

### `tether.providers.openai`

::: tether.providers.openai
    options:
      show_root_heading: false
      members_order: source

### `tether.providers.anthropic`

::: tether.providers.anthropic
    options:
      show_root_heading: false
      members_order: source

### `tether.providers.declarative`

::: tether.providers.declarative
    options:
      show_root_heading: false
      members_order: source

