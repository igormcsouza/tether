# Python SDK and Custom Tools

*For: Python developers embedding tether. After this page you can run a `Harness` and expose your own functions as tools.*

Tether's Python SDK lets you embed the micro-harness directly inside your application and expose domain-specific Python functions as POSIX-style CLI commands inside the single `act(cmd, stdin)` multiplexer.

## Turning Functions into CLI Commands with `@tool`

Decorate any synchronous or `async` Python function with `@tool`. Tether inspects your Python type annotations (`str`, `int`, `float`, `bool`, `Literal[...]`), default values, and docstring to generate:

1. A **$\le$ 12-token index line** for the static system prompt.
2. A **$\le$ 60-token `--help` specification** revealed Just-In-Time (JIT) when the agent runs `<cmd> --help` or passes invalid arguments.
3. A deterministic POSIX CLI parser that coerces types and returns self-healing usage instructions on syntax errors instead of crashing the session.

```python
from typing import Literal
from tether import Harness, tool


@tool(name="deploy", description="Trigger a service deployment")
async def deploy_service(
    service: str,
    env: Literal["staging", "prod"] = "staging",
    replicas: int = 2,
    dry_run: bool = False,
    stdin: str | None = None,
) -> str:
    """Deploy a microservice with optional release notes passed via stdin."""
    mode = "DRY-RUN" if dry_run else "LIVE"
    return f"[{mode}] Deployed {service} to {env} (replicas={replicas}) notes={stdin or 'none'}"
```

Inside the session, the LLM invokes your function through `act`:

```text
act(cmd="deploy billing-api --env prod --replicas 4", stdin=" Rollout v2.4.1 ")
```

!!! tip "Multiline Payloads via `stdin`"
    If your function includes a `stdin: str | None = None` parameter—or has a single required `str` parameter—the agent can pass multi-line code, SQL queries, JSON documents, or markdown bodies cleanly via `stdin` without complex shell escaping inside `cmd`.

## Running Sessions with `Harness`

```python
import asyncio
from tether import Harness, SandboxPolicy


async def main() -> None:
    harness = Harness(
        model="ollama/qwen3.5:9b",
        tools=[deploy_service, "mem", "web"],
        sandbox=SandboxPolicy(profile="workspace-write", workspace_root="."),
        max_steps=20,
        fold_observations_after=2,
    )

    # Run to completion in the current async loop
    session = await harness.run("Deploy billing-api to staging with 3 replicas")
    print(f"Status: {session.status} | Peak tokens: {session.peak_tokens}")
    print(session.result)

    # Send a follow-up instruction to resume the completed session
    resumed = await harness.send(session.id, "Now promote billing-api to prod")
    print(resumed.result)


if __name__ == "__main__":
    asyncio.run(main())
```

## Example: course builder

Patterns from the [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course) (`examples/course/skills/`).

### Argument parsing (v0.1.2)

- Unquoted extra words join into the **last positional `str` parameter**: `yt-candidates 1.1 outras palavras` gives `ref="1.1 outras palavras"`.
- Optional parameters need a flag: `--limit 2`.
- `*args: str` receives the words as separate positional arguments.

### Gotcha: list skill tools in `tools:` too

A skill's `tools.py` functions are registered when the skill loads, but the session only exposes names listed in the skill's `tools:`. A tool missing from that list fails with `Error: unknown command`. See [Skills](skills.md#tools-py-and-the-tools-list) ([#24](https://github.com/igormcsouza/tether/issues/24)).

### Pattern: numbered candidates

The model must never retype data such as URLs. The model chooses, the tool copies:

```text
yt-todo                 # "1.1 Arquitetura em camadas" (topics still without a video)
yt-candidates 1.1       # "1. title | channel | views" ... numbered, state kept in .yt_cands.json
yt-save 2               # tool writes the exact URL of candidate 2 to videos.md
```

```python
@tool(name="yt-save", description="Save candidate N for the topic of the last yt-candidates")
def yt_save(number: int) -> str:
    try:
        st = json.load(open(STATE))
        c = st["cands"][number - 1]
    except (FileNotFoundError, IndexError, KeyError):
        return "no such candidate; run yt-candidates <ref> first"
```

### Refuse bad input at the boundary, return the valid options

`yt-candidates` answers an unknown ref with `unknown ref; use one from yt-todo: 1.1, 1.2, ...` instead of raising. The model self-heals on the next call.

### Keep file formats safe

`videos.md` is pipe-delimited. A video title containing ` | ` corrupted it, so the tool sanitizes every field before writing:

```python
def clean(x):  # '|' is the videos.md column separator
    return x.replace(" | ", " – ").replace("|", "–").replace("\n", " ")
```

### Make multi-step edits atomic

Prefer one in-place swap over drop-then-save (delete the old row, then write the new one): if the model stops between the two steps, data is lost. Write the replacement and the removal in the same tool call.
