# One action for everything

*For: anyone curious why tether gives the model a single tool instead of a dozen. After this page you know the problem it solves, how `act` works and what it costs.*

## The problem

Most agent frameworks register fifteen to thirty separate tools (`read_file`, `write_file`, `search_web`, `run_bash`, ...). Each one is a JSON schema the model must read, remember and produce correctly. On a frontier model that is fine. A 9B model has a narrow window, so those schemas eat most of it, and it makes characteristic mistakes: it invents a key that is not in the schema, nests an object one level too deep, or picks `write_file` when it meant `run_bash`.

## What the research says

*Executable Code Actions Elicit Better LLM Agents* (Wang et al., ICML 2024) compared fragmented JSON actions with one unified action space the model writes as code. Folding many narrow schemas into one executable action improved success rates by up to 20% and shrank the prompt. The lesson is that a small, uniform action space is easier for a model than a large, varied one.

## What tether does

The model sees exactly one tool:

```text
act(cmd: str, stdin: str | None)
```

`cmd` is an ordinary command line. Everything else is a *command* behind it: `done`, `bash`, `edit`, `web`, `mem`, `agent`, and any Python function you decorate with `@tool`.

```text
act(cmd="edit replace app.py", stdin="...")
act(cmd="web search 'sqlite wal' --max 5")
act(cmd="done", stdin="Fixed the tax calculation.")
```

Anything long (file contents, a patch, a final report) goes in `stdin`, not inside a shell-escaped string in `cmd`. Models are much better at pasting text into a field than at escaping quotes and newlines.

Because the model already knows the shape of a command line from training, it needs very little to start, and tether can accept the small mistakes it makes. A few examples of what is repaired before it ever counts as an error:

- a leading `$` or wrapping backticks;
- `bash -c '...'` wrappers;
- `edit write f <<'EOF' ... EOF` (a heredoc typed into `cmd`) becomes a write with `stdin`;
- `act("done", stdin="x")` typed as text inside `cmd`;
- a tool call named `edit` instead of `act`;
- `sed -n 'a,bp file'` with the path inside the quotes.

Anything that cannot be repaired gets a one-line usage hint back, not a Python traceback ([progressive help](progressive-help.md)).

## What it costs

A command grammar to maintain: every quirk we accept is code and a test. We think that is the right place for the effort, because it is paid once, in deterministic Python, instead of on every model call.

## What we got

The fixed prompt (instructions, the `act` schema and the tool index) stays under 150 tokens, asserted by a test on every change. Against typical frameworks that spend 3,000 to 8,000 tokens before the first step, it is the difference between a small model having room to work and not.

## References

- Wang, X., et al. (2024). *Executable Code Actions Elicit Better LLM Agents (CodeAct).* ICML 2024. [arXiv:2402.01030](https://arxiv.org/abs/2402.01030)
- Decisions: [AD-1, AD-2, AD-30](../architecture/decisions.md#a-product-principles).
