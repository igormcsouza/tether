# Reference

*For: people looking up an exact flag, class, file format or message. After this page you know which reference page answers your question and where to go if you need the story instead of the facts.*

The reference is exact and complete rather than friendly. It is the right place to check **what a flag does, what a function takes or what a JSON field means**. If you are looking for how to get a job done or why something works as it does, the guides and concepts are better:

| If you want... | Go to |
|---|---|
| to get a job done, with a real example | [Guides](../guides/index.md) |
| to understand why a feature exists | [Concepts](../concepts/index.md) |
| the exact answer to "what does this do" | this section |

## Find the page by question

| Question | Page |
|---|---|
| What flags does `tether run` take? What exit code means what? | [CLI](cli.md) |
| How do I declare a provider, set a timeout or pass a parameter? | [Model providers](providers.md) |
| What exactly does `bash`, `edit`, `web`, `mem` or `agent` accept? | [Built-in tools](tools.md) |
| What does the JSON from `tether run --json` and the MCP tools look like? | [Agent interface](agent-interface.md) |
| How do I use `Harness` or `Pipeline` from Python? | [Harness and CLI (API)](harness.md) |
| How is a session stored? How does folding decide? | [Context and SQLite store](context-and-store.md) |
| How does `act` parse a command? How do I write a `@tool`? | [Multiplexer and decorator](multiplexer-and-decorator.md) |
| What does the sandbox allow? What goes in a skill file? | [Sandbox and skills](sandbox-and-skills.md) |

The API pages are generated from the docstrings in the source, so they cannot drift from the code. The pages that are written by hand (CLI, providers, agent interface, context and store) state the rules the code follows and name the settings that change them.

## Conventions

- **Model names** are `provider/model` (`ollama/qwen3.5:9b`). With no prefix, `ollama/` is assumed.
- **Exit codes** are the same everywhere: `0` completed, `1` usage error, `2` waiting for input (also stuck or out of steps), `3` a verify gate failed, `5` worker error, `6` a wait timed out, `130` interrupted.
- **Environment variables** are listed with the feature they change (`TETHER_DB`, `TETHER_PROVIDERS`, `TETHER_GATE_TIMEOUT`, `OLLAMA_HOST`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...). Keys are always read from the environment, never from a file in the project.
- **Words** such as *session*, *gate*, *fold* and *step* are defined in the [glossary](../glossary.md).
