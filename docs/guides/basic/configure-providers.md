# Configure providers and models

*For: people who want to use more than the default local model. After this page you can create your `providers.yaml`, point tether at Ollama on another machine, an OpenAI-compatible gateway, Anthropic or another command-line tool, and tune a model with parameters.*

A **model name** in tether is `provider/model`: `ollama/qwen3.5:9b`, `openai/gpt-4o-mini`, `anthropic/claude-3-7-sonnet-latest`. With no prefix, tether assumes `ollama/`. The built-in providers work with an environment variable alone, so you only need the file for your own endpoints.

## Without any file

```sh
# local Ollama (default)
tether run --model ollama/qwen3.5:9b "..."

# OpenAI, or anything that speaks its protocol (OpenRouter, vLLM, Groq)
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://openrouter.ai/api/v1      # optional
tether run --model openai/gpt-4o-mini "..."

# Anthropic
export ANTHROPIC_API_KEY=...
tether run --model anthropic/claude-3-7-sonnet-latest "..."
```

If Ollama is on another port or machine, set `OLLAMA_HOST=http://host:11434`.

## Create the file

```sh
mkdir -p ~/.tether && $EDITOR ~/.tether/providers.yaml
```

Each top-level key becomes a model prefix. This file declares one of each kind:

```yaml
nvidia:                      # tether run --model nvidia/nvidia/nemotron-3-ultra-550b-a55b
  kind: openai               # any OpenAI-compatible server
  base_url: https://integrate.api.nvidia.com/v1
  api_key_env: NVIDIA_API_KEY      # the NAME of the variable, never the key
  rpm: 36                          # at most 36 requests a minute

gpu-box:                     # tether run --model gpu-box/qwen3.5:9b
  kind: ollama               # an Ollama on another machine
  host: http://gpu-box:11434
  context_tokens: 32768

claude-cli:                  # tether run --model claude-cli/sonnet
  kind: command              # wrap any program that reads a prompt and prints JSON
  argv: [claude, -p, --model, "{model}", --tools, "", --system-prompt, "{system}", --output-format, json]
  stdin: "{conversation}"
  reply: result              # where the answer is in the JSON the program prints
  timeout: 180
```

Run `tether doctor` afterwards. It reports `providers.yaml: ...` with the entry name if something is invalid, instead of failing later in the middle of a task.

## Why it works this way

- **The file lives in your home, not in the project.** If tether read providers from the working folder, cloning a stranger's repository could redirect your model calls and your API key to their server.
- **Keys are variable names.** `api_key_env: NVIDIA_API_KEY` means the file is safe to share or commit. A missing or empty variable fails the run before any request, and the error names the variable, never its value.
- **You cannot replace a built-in prefix.** `ollama`, `openai`, `anthropic` and `claude` always mean what they say.
- **A `command` provider is never run through a shell.** Tether starts the program directly with your arguments, so a prompt cannot inject shell syntax.

## Tune a model

Tether sets no temperature or other sampling value of its own: the model's defaults apply. If you want one, set it in the entry or on one call:

```yaml
nvidia:
  kind: openai
  base_url: https://integrate.api.nvidia.com/v1
  api_key_env: NVIDIA_API_KEY
  params: {temperature: 0, reasoning_effort: low}
```

```sh
tether run --model nvidia/nvidia/nemotron-3-ultra-550b-a55b --param temperature=0.7 "..."
```

A call beats the file, and the file beats the adapter's default. Other per-entry knobs:

| Key | Meaning |
|---|---|
| `context_tokens` | How much the model may see at once (default 32,768) |
| `timeout` | Seconds before a request is abandoned; HTTP providers retry twice first |
| `rpm` | Requests per minute across all your tether processes (a free tier's limit) |
| `fold_after` | Fix how soon old outputs are folded ([how folding works](../../concepts/context-and-folding.md)) |

## When it fails

Failures name what to do: an Ollama model that is not installed lists the ones that are; a 401 or 403 names the variable to set; a usage limit shows the provider's own words once instead of retrying. See [Troubleshooting](../../troubleshooting.md) for each message.

The complete schema, every key and the exact retry rules are in the [providers reference](../../reference/providers.md). To plug in a transport that is not HTTP or a command, see [Custom providers and transports](../advanced/custom-providers-and-transports.md).
