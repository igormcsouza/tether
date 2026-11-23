# Search the web and write a summary

*For: anyone who wants to see tether do something useful in one command. After this page you can give a local model web access, ask for a sourced summary, and see exactly what it looked at.*

A small local model cannot know what is new in Python 3.14. But it can search, open the real pages and summarise them, if you let it. That is the whole idea of tether tools: nothing is on by default, so you switch on only what the job needs. Here that is `web`.

## Run it

```sh
tether run --tools web --max-steps 15 \
  "Search the web for what is new in Python 3.14 and write a summary of the 3 most important changes, with the source URL for each."
```

`--tools web` is the only thing the model may use besides `done`. `--max-steps 15` is a safety net: if the model wanders, tether stops it and hands the task back instead of running for ever.

The model is the default one, `qwen3.5:9b` on a laptop GPU. This is its answer, word for word. It took 1 minute 45 seconds and 9 steps:

```text
# Summary of Python 3.14's Most Important Changes

Python 3.14 (released October 2025) introduces several significant changes to the language and standard library. Here are the three most important:

## 1. Deferred Evaluation of Annotations (PEP 649 & PEP 749)
Python 3.14 changes how annotations are evaluated. Instead of being evaluated eagerly at definition time, annotations are now stored in `__annotate__` functions and evaluated only when necessary (unless `from __future__ import annotations` is used). This improves performance and makes forward references work without string quoting. A new `annotationlib` module provides tools to inspect annotations in different formats (VALUE, FORWARDREF, STRING).

**Source:** https://peps.python.org/pep-0749/

## 2. Template Strings (PEP 750)
Python 3.14 adds a new `t` prefix for template strings, which generalize f-strings. Template strings evaluate to a `Template` type that provides access to both string parts and interpolated values before they're combined. This enables secure string processing, HTML templating, and safe interpolation that f-strings cannot support.

**Source:** https://peps.python.org/pep-0750/

## 3. Multiple Interpreters in the Standard Library (PEP 734)
CPython now exposes support for running multiple Python interpreters in the same process via the new `concurrent.interpreters` module. This enables a CSP-like concurrency model and true multi-core parallelism while staying within a single process for better efficiency than multiprocessing.

**Source:** https://peps.python.org/pep-0734/
```

## See what it did

A good answer you cannot check is worth little. Tether keeps every step, so you can:

```sh
tether read ses_9fa4ba2f --steps
```

```text
[step 1] web:search "Python 3.14 new features changes"
[step 2] web "Python 3.14 new features changes"
[step 3] web search "Python 3.14 new features" --max 5
[step 4] web fetch "https://docs.python.org/3/whatsnew/3.14.html"
[step 5] web fetch "https://docs.python.org/3/whatsnew/3.14.html" --from 'ed to emerge for'
[step 6] web fetch "https://peps.python.org/pep-0750/"
[step 7] web fetch "https://peps.python.org/pep-0749/"
[step 9] done
```

Look at steps 1 and 2: the model typed the command wrong (`web:search`, then `web` with no verb). Tether did not crash and did not waste the step. It answered with the correct usage, and the model fixed itself on step 3. That small self-correction is a big part of why a 9B model can finish jobs that normally need a frontier model.

Step 4 opened a long page, and step 5 asked for just the part that matters (`--from`). Long pages never fill the model's memory: tether keeps the full text in a local database and shows the model a short piece (see [how folding works](../concepts/context-and-folding.md)).

## Try it yourself

- Change the question: `"Search the web for the three most common causes of SQLite 'database is locked' and summarise them with sources."`
- Ask for a file instead of text: add `--tools web,edit` and end the goal with `Save it as summary.md.`
- Use a bigger model for the same job: `--model nvidia/nvidia/nemotron-3-ultra-550b-a55b` (the [Nemotron page](script-with-nemotron.md) shows how to set that up).

## Where to go next

- [Let Claude call tether](review-with-claude.md) so your main assistant hands this kind of reading work to a cheaper model.
- [Built-in tools](../guides/basic/built-in-tools.md) shows `web`, `bash`, `edit`, `mem` and `agent` with real examples.
