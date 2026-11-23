# Write and check a script with Nemotron

*For: anyone who wants a model to write code and prove it works. After this page you can point tether at a hosted model, let it create files, and use a check command so "done" means done.*

Local models are great for reading and small edits. For writing a whole script it can pay to use a bigger model. NVIDIA offers Nemotron 3 Ultra, a 550-billion-parameter model, on a free tier, and tether talks to it like any other provider.

## Set up the provider once

Tether finds providers in `~/.tether/providers.yaml`. Put your key in an environment variable (never in the file), then add:

```yaml
nvidia:
  kind: openai                                  # NVIDIA's API speaks the OpenAI protocol
  base_url: https://integrate.api.nvidia.com/v1
  api_key_env: NVIDIA_API_KEY                   # the NAME of the variable, never the key itself
  rpm: 36                                       # the free tier allows 40 requests a minute
```

```sh
export NVIDIA_API_KEY=...        # your key from build.nvidia.com
```

The model name is `provider/model`, so Nemotron is `nvidia/nvidia/nemotron-3-ultra-550b-a55b` (the first `nvidia` is *your* provider entry, the rest is NVIDIA's own model id). The full format of this file is in [Model providers](../reference/providers.md).

## Ask for a script and a check

```sh
tether run --model nvidia/nvidia/nemotron-3-ultra-550b-a55b \
  --tools bash,edit --max-steps 20 \
  --verify 'test "$(python3 wordcount.py sample.txt | wc -l)" -eq 5' \
  "Create wordcount.py: a script that takes a text file path and prints the 5 most common words with their counts, one per line as 'word count', ignoring case and punctuation. Also create sample.txt with a few sentences to try it on."
```

Two things make this more than "ask a model for code":

- `--tools bash,edit` lets the model run commands and write files, and nothing else.
- `--verify` is your check. Tether runs it itself, inside the sandbox, before it accepts `done`. If it fails, the model sees the output and keeps working. The model cannot just claim it is finished.

It finished in 6 steps and 22 seconds, and said:

```text
Created wordcount.py and sample.txt successfully.

Test run output:
the 5
quick 4
fox 4
dog 3
a 3
```

## What it did

```sh
tether read ses_ed3a5a1c --steps
```

```text
[step 1] cat > sample.txt << 'EOF' ...
[step 2] cat > wordcount.py << 'EOF' ...
[step 3] python3 wordcount.py sample.txt
         the 5 / quick 4 / fox 4 / dog 3 / a 3
[step 4] cat sample.txt
[step 5] cat wordcount.py
...
```

It wrote the data first, then the script, ran it, and re-read both files to check its own work before saying done. The gate then ran once more on tether's side.

## A mistake you can learn from

An earlier run of the same task used a weaker check, `python3 wordcount.py sample.txt | head -3`, which would also pass for a script that prints three lines of nonsense. A gate is only as good as what it tests. Make it fail for the wrong answer (here, a line count and not just "it ran").

That earlier run also shows tether helping with a small slip. On step 3 the model typed `python wordcount.py`:

```text
[step 3 tool] Error: unknown command `python`. Enabled tools: done, bash, edit. Enable more: ...
[step 4 tool] bash: line 1: python: command not found    [exit 127]
[step 5]      python3 wordcount.py sample.txt            the 3 / a 3 / quick 2 / brown 2 / fox 2
```

The error told the model what it could do, and it corrected itself in two steps, with no human involved.

## The file it wrote

```python
import sys
import re
from collections import Counter

def main():
    if len(sys.argv) != 2:
        print("Usage: python wordcount.py <file_path>")
        sys.exit(1)
    with open(sys.argv[1], 'r') as f:
        text = f.read()
    words = re.findall(r'\b\w+\b', text.lower())
    for word, count in Counter(words).most_common(5):
        print(f"{word} {count}")

if __name__ == "__main__":
    main()
```

This is the core of it; the model also added a message for a missing file.

## Where to go next

- [Fix a failing test](../guides/basic/fix-a-failing-test.md) uses the same `--verify` idea on a local model.
- [Choose a model](../guides/basic/choose-a-model.md) compares what each model is good at.
- [Run it on its own branch](../guides/advanced/own-branch.md) so generated code never touches your working copy.
