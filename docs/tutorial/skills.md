# Progressive Skills

Skills let you package domain-specific instructions, preferred model defaults, enabled built-in tools, and custom `@tool` Python functions into a self-contained unit.

Tether searches for skills in:

1. `./skills/` (workspace skills)
2. `~/.tether/skills/` (user-global skills)

## Skill Structure

A skill can be either a single Markdown file (`skills/<name>.md`) or a directory (`skills/<name>/SKILL.md`) with an optional companion `skills/<name>/tools.py`:

```text
skills/
└── analyst/
    ├── SKILL.md
    └── tools.py
```

### `SKILL.md`

```markdown
---
name: analyst
description: Financial ratio and margin analysis
model: ollama/qwen3.5:9b
tools: [web, mem, calc-margin]
---
You are a quantitative financial analyst.
1. Use `calc-margin` to verify gross and operating margins.
2. Pin verified metrics with `mem pin` before synthesizing your report.
```

### Companion `tools.py`

Any `@tool`-decorated function in `skills/<name>/tools.py` is automatically registered into the session's multiplexer when the skill is loaded:

```python
from tether import tool


@tool(name="calc-margin", description="Compute profit margin percentage")
def calc_margin(revenue: float, cost: float) -> str:
    """Calculate profit margin percentage from revenue and cost."""
    return f"{((revenue - cost) / revenue) * 100:.2f}%"
```

Small models rarely quote arguments, so extra unquoted words join into the last `str` parameter (`yt-search arquitetura em camadas` with `def yt_search(query: str, limit: int = 3)` gives `query="arquitetura em camadas"`; set `limit` with `--limit 2`). A `*args: str` parameter receives the words as separate positional arguments.

## Using a Skill

=== "CLI"

    ```sh
    tether run --skill analyst "Evaluate Q3 revenue of $420M against cost of $115M"
    ```

=== "Python SDK"

    ```python
    from tether import Harness

    harness = Harness(skill="analyst")
    
    # Or load dynamically mid-session if the `skill` tool is enabled:
    # act(cmd="skill list")
    # act(cmd="skill load analyst")
    ```
