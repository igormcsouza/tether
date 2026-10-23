# Extending Tether

Tether is designed around small, explicit protocols so you can plug in custom model gateways, local inference engines, or domain tool suites without subclassing framework base classes.

## 1. Custom Model Providers (`ModelProvider` & `register_provider`)

Out of the box, Tether includes three `httpx` adapters:

- `ollama/<model>` (`OllamaProvider`)
- `openai/<model>` (`OpenAIProvider` — works with OpenAI, vLLM, Groq, OpenRouter, Together)
- `anthropic/<model>` (`AnthropicProvider`)

If you want to route model calls through an internal corporate gateway, a custom local inference runner, or a deterministic test harness, implement the `ModelProvider` protocol (`async def generate(messages, tools) -> ModelResponse`) and register a prefix with `register_provider`:

```python
import asyncio
from typing import Any
from tether import (
    Harness,
    ModelResponse,
    extract_fallback_action,
    register_provider,
)


class CustomGatewayProvider:
    """Example custom provider implementing the ModelProvider protocol."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        # Call your custom transport, gateway, or local inference engine here
        raw_output = f'act("done", stdin="Processed by {self.model_name}")'
        return ModelResponse(
            content=raw_output,
            action=extract_fallback_action(raw_output),
            prompt_tokens=128,
        )


# Register under a custom `<prefix>/<model_name>` scheme
register_provider("gateway", lambda model_name: CustomGatewayProvider(model_name))


async def main() -> None:
    harness = Harness(model="gateway/qwen-internal-32b")
    session = await harness.run("Verify custom gateway routing")
    print(session.result)


if __name__ == "__main__":
    asyncio.run(main())
```

You can also pass a `provider` instance directly to `Harness(provider=CustomGatewayProvider("..."))` for one-off sessions or unit tests.

---

## 2. Custom `ToolSpec` Namespaces

For simple single-command tools, the `@tool` decorator is all you need. If you want to build a multi-subcommand namespace like `web` (`web search`, `web fetch`) or `mem` (`mem pin`, `mem search`, `mem recall`), construct a `ToolSpec` directly:

```python
from tether import Harness, ToolSpec


async def _git_dispatch(**kwargs: object) -> str:
    raw_args = str(kwargs.get("args", "")).strip()
    if raw_args in ("", "status"):
        return "On branch main — working tree clean"
    return f"Executed git {raw_args}"


git_tool = ToolSpec(
    name="git",
    description="Inspect repository status and history",
    fn=_git_dispatch,
    params=[],
    accepts_stdin=False,
    is_async=True,
    usage_override=(
        "Usage: git <status|log|diff>\n"
        "Inspect repository state.\n"
        "  git status : Show working tree status"
    ),
)

harness = Harness(tools=[git_tool])
```

## Command normalizers

Models bring habits the `act` grammar does not expect (wrapping commands in `bash -lc '...'`, prefixing a vendor tag). Built-in fixes live in `tether.multiplexer.NORMALIZERS`; add your own with `tether.register_normalizer(fn)`, a deterministic `str -> str` that returns its input unchanged when it does not apply. It runs for every model after the built-ins, before the command is parsed.

```python
import tether


@tether.register_normalizer
def drop_vendor_prefix(cmd: str) -> str:
    return cmd.removeprefix("vendor:")
```
