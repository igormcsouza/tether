# Custom providers and transports

*For: developers adding tools or model backends. After this page you can extend tether without touching its core.*

Tether is designed around small, explicit protocols so you can plug in custom model gateways, local inference engines, or domain tool suites without subclassing framework base classes.

## 1. Custom Model Providers

Out of the box tether talks to Ollama, OpenAI-compatible servers and Anthropic. To reach anything else (an internal gateway, a custom inference runner, a replay harness for tests) declare it in `providers.yaml` or register a Python class with `register_provider`. Both routes, with worked examples, are on one page: [Model providers](../../reference/providers.md).

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

## Check that tether sees your provider

A provider declared in `providers.yaml` shows up in the setup check, and an invalid entry is reported by name:

```text
ok   providers  5 declared
```

```text
FAIL providers  providers.yaml: entry `my-gateway` has unknown kind `opneai`. Valid kinds: openai, ollama, anthropic, command.
```

A provider you register in Python (`register_provider`) lives in your program, not in a file, so `tether doctor` does not list it. Run a one-line task through `Harness(model="<prefix>/<model>")` to prove it works.

## When it goes wrong

- **`unknown command` after registering a normalizer.** A normalizer rewrites the text of `cmd` before parsing; it cannot add a tool. Enable the tool with `tools=[...]`.
- **A prefix you registered is ignored.** `ollama`, `openai`, `anthropic` and `claude` are built in and cannot be shadowed. Pick another prefix.
- **A transport works once and then times out.** Tether retries a timeout twice; set `timeout:` on the entry, or raise it in your adapter.
- More messages and their fixes: [Troubleshooting](../../troubleshooting.md).
