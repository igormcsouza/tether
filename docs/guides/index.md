# Guides

*For: people who want to get the most out of tether. Each guide is one job, with a real command and real output. After this section you know what tether can do and which feature to reach for.*

The guides come in two groups. **Basic usage** is what you need every day. **Advanced** is what makes tether different from a plain chat with a model: checks, pipelines, sub-agents, sandboxes, your own tools and providers.

## Basic usage

| I want to... | Guide |
|---|---|
| know where tether keeps things and how to check my setup | [Find your way around](basic/find-your-way-around.md) |
| start a task, leave it running, come back to it | [Run and manage sessions](basic/run-and-manage-sessions.md) |
| decide what the model may touch | [Built-in tools](basic/built-in-tools.md) |
| point tether at Ollama, OpenAI, Anthropic, a gateway or another CLI | [Configure providers and models](basic/configure-providers.md) |
| know which model to pick for which job | [Choose a model](basic/choose-a-model.md) |
| have a model fix a failing test and prove it | [Fix a failing test](basic/fix-a-failing-test.md) |
| write a task a small model can finish | [Write tasks a small model can finish](basic/write-tasks-small-models.md) |
| see what a session did and why it went wrong | [Review and debug a session](basic/review-and-debug.md) |
| keep instructions and tools for a kind of job in one place | [Skills](basic/skills.md) |

## Advanced

| I want to... | Guide |
|---|---|
| call tether from Python and give the model my own functions | [Python SDK and custom tools](advanced/sdk-and-custom-tools.md), [Give the model a tool of your own](advanced/add-your-own-tool.md) |
| run a job in stages, each with its own model and checks | [Pipelines](advanced/pipelines.md) |
| split work across parallel sub-agents | [Multi-agent orchestration](advanced/multi-agent.md) |
| keep generated code off my working copy | [Run a session on its own branch](advanced/own-branch.md) |
| decide exactly what a session can read, write and reach | [Security and sandbox](advanced/security-and-sandbox.md) |
| use checks, memory and statistics to improve over time | [Gates, memory and telemetry](advanced/gates-memory-telemetry.md) |
| cap time, tokens and resources | [Control cost and limits](advanced/control-cost-and-limits.md) |
| delegate work from Claude Code, Codex or Cursor | [Delegate from your agent](advanced/delegate-from-your-agent.md), [Use tether inside your agent (MCP)](advanced/use-from-your-agent-mcp.md) |
| plug in my own model gateway | [Custom providers and transports](advanced/custom-providers-and-transports.md) |

Some features work differently from what you may know from other agent tools. Where that is the case the guide says why tether chose it, and the [decisions register](../architecture/decisions.md) has the full list.
