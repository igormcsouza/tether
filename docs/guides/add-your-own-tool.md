# Give the model a tool of your own

*For: Python developers who want the model to call their code. After this page you can turn a function into a tool, run it with a local model, and know what the model sees.*

Tether exposes exactly one tool schema to the model, `act(cmd, stdin)`. Your function becomes a **command** behind it, so adding ten tools does not add ten schemas to the prompt.

## The function

```python
import asyncio

from tether import Harness, tool

PRICES = {"apple": 0.5, "pear": 0.75, "melon": 3.2}


@tool(name="price", description="Look up the unit price of a fruit")
def price(fruit: str) -> str:
    """Return the price of one `fruit` in euros. Known fruit: apple, pear, melon."""
    if fruit not in PRICES:
        return f"Unknown fruit `{fruit}`. Known: {', '.join(PRICES)}."
    return f"{fruit}: {PRICES[fruit]:.2f} EUR"


async def main() -> None:
    harness = Harness(model="ollama/qwen3.5:9b", tools=[price])
    session = await harness.run("What do 3 pears and 1 melon cost together? Use the price tool.")
    print(session.status, "-", session.result)


asyncio.run(main())
```

Type hints and the docstring become the command's usage text. The model only sees the one-line description until it runs `price --help` or calls it wrongly, so a tool costs about a dozen prompt tokens until it is used.

## Run it

```bash
python shop.py
```

```text
COMPLETED - 5.45 EUR
```

Ten seconds, three steps: the model asked for the pear price, then the melon price, then did the sum (3 × 0.75 + 3.20 = 5.45) and finished. Note what the tool does on bad input: it returns the list of valid fruit and does not raise. A message that says what to do next is how a small model recovers on its own.

## Make the error message do the work

Write tool errors for a reader that cannot ask a follow-up question: say what was wrong, list the valid options and show the next call. A tool that raises a stack trace teaches the model nothing.

## Other ways to add things

- **In a skill.** Put the function in `skills/<name>/tools.py` and list its name under `tools:` in `SKILL.md`; tools are opt-in, so an unlisted tool stays unavailable.
- **A model backend, not a tool.** Declare it in `~/.tether/providers.yaml` or register a class: [Model providers](../reference/providers.md).

## When it goes wrong

- **`unknown command` for your tool.** It was not passed in `tools=[...]` (or not listed in the skill's `tools:`).
- **The model passes the wrong argument.** Tether answers with the tool's usage line; if it keeps happening, tighten the docstring and the error message.

More: [Python SDK and custom tools](../tutorial/sdk-and-custom-tools.md), [Extending tether](../extending.md).
