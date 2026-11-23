# Help only when asked

*For: anyone curious how tether keeps its prompt small while still telling the model how every tool works. After this page you know what the model is told, and when.*

## The problem

Even with one `act` tool, the model must know what `edit`, `web` and your own tools do. Putting every flag of every command in the prompt brings back the cost we removed.

## What the research says

*SWE-agent* (Yang et al., NeurIPS 2024) showed that the interface between an agent and the computer matters as much as the model. Raw shell access and verbose output hurt; a purpose-built *agent-computer interface* with compact documentation and feedback that explains failures helps a lot. The point is not more help, but help at the right moment.

## What tether does

The prompt lists one short line per enabled tool, at most about twelve tokens:

```text
- done: Complete task and submit final de...
- bash: Execute sandboxed shell commands
- edit: View, create, or patch workspace...
- web: Search the web or fetch clean URL...
```

Full usage appears only when the model asks for it (`web --help`) or gets something wrong, and it is capped at about sixty tokens. This is the real answer to a bare `web`:

```text
Usage: web search <query> [--max 5] | web fetch <url>[#anchor] [--from <text>]
Desc : Search the web or fetch clean markdown text from a URL.
```

A wrong call never ends in a traceback. It ends in a message that says what to do: a missing argument shows the usage; an unknown command lists the enabled tools and how to enable more; a tool that exists but is switched off says it is disabled.

You can watch this happen in a real run. A model typed `web:search "..."`, then `web "..."`, and on the third step used `web search "..." --max 5` correctly ([the search example](../start/search-and-summarize.md)). Two steps were spent learning, none were lost to a crash.

## What it costs

Each hint costs a step. That is cheaper than carrying every tool's full text in every prompt, and the hints are history rather than prefix, so they never disturb the cache ([see why](kv-cache-and-static-prefix.md)).

## What we got

Index lines stay under 12 tokens and usage under 60, both checked by tests. Self-correction after a hint is common even on 9B models, which is why `syntax_error` events show up in [`tether stats`](../guides/basic/review-and-debug.md) as friction to watch, not as failures.

## References

- Yang, J., et al. (2024). *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering.* NeurIPS 2024. [arXiv:2405.15793](https://arxiv.org/abs/2405.15793)
- Decisions: [AD-31](../architecture/decisions.md#f-the-action-layer).
