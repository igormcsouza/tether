# Python SDK and Custom Tools

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
