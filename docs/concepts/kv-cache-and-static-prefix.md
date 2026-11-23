# A prefix that never changes

*For: anyone who wants to know why tether never edits the start of a conversation, even when it would be convenient. After this page you know what the cache is and which tether behaviours exist to protect it.*

## The problem

Every time a model answers, the server first reads the whole conversation so far. Local servers (Ollama, llama.cpp, vLLM) and hosted ones (Anthropic's prompt caching, OpenAI's prefix caching) avoid redoing that work: they keep the computed state of the start of the conversation, and reuse it if the next request begins with exactly the same text. One changed character near the top and everything after it is computed again.

On a laptop GPU that is the difference between an answer in a second and an answer in ten. On a hosted model it is the difference between paying full price and paying a fraction.

## What tether does

The rule is simple and absolute: **the beginning of the conversation never changes while a session runs.**

- The system prompt and the `act` tool description are built once and never edited. A tool you did not enable at the start is never added later.
- Notes and nudges ("you have not changed anything for six steps") are appended to the output of the step they concern. They are history, not prefix.
- Your pinned notes (`mem pin`) go on the last message, not near the top, so every earlier message stays identical from step to step.
- Past tool calls are replayed in exactly the same form each time, with their input shown as a fixed 400-character prefix.
- On Anthropic, the system prompt and tool description are marked as cacheable.

This is also why [`tether retro`](../guides/basic/review-and-debug.md) only ever proposes edits you apply later, and never rewrites instructions while a session is running.

## What it costs

You cannot "add a tool now". If a task turns out to need `web`, start the session with it, or let the model ask you and continue it with `send` (a continuation is a new request with the same prefix, so the cache still holds).

## What we got

Folding old output rewrites messages in the middle of the history, which does change what the server has cached from that point on. That is why folding is as-needed instead of on a timer ([context and folding](context-and-folding.md)): it keeps the number of rewrites as low as the window allows. Whether folding costs more in lost caching than it saves in prompt size on a paid model is not measured yet; it is an [open question](../architecture/decisions.md#open-questions).

## References

- Decisions: [AD-3, AD-18, AD-29](../architecture/decisions.md#a-product-principles).
