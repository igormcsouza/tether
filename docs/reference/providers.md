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
