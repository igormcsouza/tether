# The deterministic envelope

*For: anyone who wants to know how tether decides a task is finished, and why the model's own "done" is not enough. After this page you know what the harness decides without asking the model.*

## The problem

A small model has two bad habits at the end of a task. It declares victory early ("I have fixed it") without checking. Or it does the work, then keeps re-running the tests until it runs out of steps without ever saying it is done. Either way the user cannot tell from the model's words whether the work is finished.

## What the research says

*LLM-Native Applications as a Paradigm for AI-Driven Software Architecture* (Maia et al., 2026) argues for a hard split. The model is a probabilistic kernel good at proposing the next move. Everything that must always be true (what is allowed, what is stored, when the work is complete) belongs in a deterministic envelope the model cannot talk its way past.

## What tether does

**The model only picks the next command.** Parsing it, running it, jailing it, recording it, deciding what to show next and deciding the task is over are all ordinary code.

**A task ends only when the envelope says so.**

- Plain text without a command never ends a session. The harness answers with a short nudge. If the text looks like a real answer (80 characters or more), the nudge says it was not delivered and asks the model to pass it to `done`; if the session ends stuck, that reply is shown in the result, marked as unconfirmed.
- With `--verify "pytest -q"`, tether runs your command itself, inside the sandbox, when the model calls `done`. If it fails, the model gets the output and keeps working. If it passes, the session is `COMPLETED`.
- If the model did the work and then stalls without calling `done`, and every verification command passes, tether ends the session as completed: "Finished by the harness". The check you chose is the completion criterion, not the model's habit of saying so.
- With no `--verify`, the model's own last passing test run counts, if nothing changed since and it is still green when tether runs it again.
- A check that cannot run at all (the program does not exist, the command is empty) fails the session before the first model call, with no tokens spent.

**When it cannot finish, it hands back, it does not guess.** Out of steps, out of budget or stuck: the session ends `WAITING_INPUT` with a summary and, if the model offered one, its last answer. You decide whether to `send` more guidance.

## What we measured

A verification gate by itself is **not** a performance lever. Adding it to the 20 failing Polyglot exercises gained +0.08 in mean score and one pass. We keep it because it makes the result *trustworthy*, not because it raises the score. The real effect of the envelope shows in what did not happen: in one benchmark 8 of 36 runs wasted 1 to 13 steps because a bare `done` was rejected, and two runs that scored 1.0 were marked failed. After the fix, the steps lost to a rejected `done` went from 18 to 0. The pass count did not move (the runs that still failed never called `done` at all), which is the honest reading: the envelope removes a way to lose, it does not make a weak model stronger.

## What it costs

You have to write a check to get the strongest guarantee. A weak check is a weak guarantee ([the example on the start page](../start/script-with-nemotron.md)).

## References

- Maia, P. H. M., et al. (2026). *LLM-Native Applications as a Paradigm for AI-Driven Software Architecture.*
- Decisions: [AD-4, AD-19, AD-22, AD-23](../architecture/decisions.md#d-the-loop).
