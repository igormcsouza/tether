# 🪢 Tether

**A general-purpose, headless-first LLM-Native micro-harness engineered for small context windows and high-signal business logic.**

[![PyPI](https://img.shields.io/pypi/v/tether-sdk?color=0d9488&label=PyPI%20%7C%20tether-sdk)](https://pypi.org/project/tether-sdk/)
[![Docs](https://img.shields.io/badge/Docs-igormcsouza.github.io%2Ftether-0d9488)](https://igormcsouza.github.io/tether/)
[![Architecture Paradigm](https://img.shields.io/badge/Paradigm-LLM--Native%20(Maia%20et%20al.%2C%202026)-6366f1)](#theoretical-foundation)
[![Target Models](https://img.shields.io/badge/Models-Ollama%20(qwen3.5%3A9b)%20%7C%20Claude%20%7C%20GPT-10b981)](#multi-model-zero-bloat-adapters)
[![Python](https://img.shields.io/badge/Python-3.12%2B%20%7C%20uv%20%7C%20SQLite%20WAL-3b82f6)](#quickstart)

---

## Why Tether?

Modern agent frameworks treat context windows as infinite dumping grounds. Before your application processes a single line of business logic, typical harnesses inject **3,000–8,000+ tokens** of verbose JSON tool schemas, sprawling system prompts, and unpruned execution traces.

On frontier cloud models, that waste is expensive. On local and small models like **`qwen3.5:9b`**, it is fatal:
1. **Attention Dilution:** Flooding the prompt with dozens of unused tool schemas degrades reasoning accuracy on the actual domain task.
2. **Structured-Output Fragility:** Small models frequently hallucinate escaping or nested JSON structures when forced to choose among 20+ complex function-calling schemas.
3. **KV-Cache Thrashing:** Dynamically mutating the `tools` array between turns invalidates prefix caches in local inference servers (`Ollama`, `llama.cpp`, `vLLM`), tanking latency.

**Tether** keeps your LLM, tools, skills, and sub-agents tied together with near-zero overhead—starting with **zero tools loaded by default** and reserving **>90% of the active context window** for your domain problem.

---

## Theoretical Foundation

Tether is not just another wrapper around chat completions; every design choice is grounded in recent systems and software-architecture research on why LLM agents succeed or fail:

1. **Probabilistic Core, Deterministic Envelope ([Maia et al., 2026](#references)):**
   Rather than trusting the model to enforce its own guardrails or manage state in raw text, Tether separates the **probabilistic reasoning kernel** (the LLM) from a **strictly deterministic envelope** (CLI argument parsing, path canonicalization, OS kernel sandboxing, SQLite ACID state transitions, and explicit `done` termination gates).
2. **Why a Single `act(cmd, stdin)` Primitive Beats 30 JSON Schemas ([Wang et al., ICML 2024 — *CodeAct*](#references)):**
   Across 17 evaluated models, Wang et al. demonstrated that forcing an LLM to choose among dozens of rigid JSON function-calling schemas degrades reasoning and wastes thousands of prompt tokens. Consolidating actions into a **single unified executable action channel** improves task success rates by **up to 20%** while cutting required turns by **~30%**—an effect that is especially pronounced on smaller open-weight models (`7B`–`9B`).
3. **Why a Virtual CLI + Progressive `--help` + Observation Folding ([Yang et al., NeurIPS 2024 — *SWE-agent*](#references)):**
   Just as humans need ergonomic UIs, LLMs need purpose-built **Agent-Computer Interfaces (ACIs)**. Following Yang et al., Tether replaces raw shell dumps and upfront schema walls with a compact POSIX-style command bus, windowed line-numbered file editing (`edit view`/`replace`), immediate self-healing usage hints (`--help`) when a command is malformed, and **ephemeral observation folding** so old tool outputs don't crowd out active reasoning.
4. **Context as L1 Cache Backed by SQLite L2 Storage ([Packer et al., 2023 — *MemGPT*](#references)):**
   Instead of treating the prompt as an unbounded append-only transcript, Tether treats the active context window like an **OS L1 working cache** (static prefix + `mem pin` scratchpad + the last $K$ raw observations) backed by **L2 disk storage** (`.tether/tether.db` in WAL mode with an automatic FTS5 BM25 index), allowing agents to page relevant knowledge in and out on demand via `mem search`, `mem recall`, and `agent query`.

---

## Core Pillars of Tether `v0`

### 1. Virtual CLI Multiplexer + Progressive `--help`
Instead of registering dozens of JSON schemas with the model provider, Tether exposes **only one static JSON tool** (`act(cmd: str, stdin: str | None = None)`) and routes all capabilities through a virtual POSIX-style command bus:
- **Zero Tools by Default:** Start completely bare (`done` only), or opt-in to specific tools via CLI (`--tools web,bash` or `--tools all`), Python SDK (`tools=["web"]`), or Skill frontmatter.
- **1-Line Toolbox Index:** Active tools appear as a compact 1-line summary in the static prompt prefix (~10 tokens per tool).
- **JIT Schema Disclosure (`--help`):** Full flags and docstrings are disclosed only when the model runs `<cmd> --help` or makes an argument error (self-healing usage hint).
- **Explicit Termination (`act("done", stdin="...")`), Interactive Inquiry (`done --ask`), & Pre-`done` Verification Gates:** Small models often think out loud mid-task or prematurely claim completion. Tether requires an explicit `act("done", stdin="final report")` call, supports zero-bloat interactive clarification via `act("done --ask", stdin="question")` (cleanly suspending the session in `WAITING_INPUT`), and can enforce zero-token **deterministic pre-`done` verification gates** (`--verify "pytest -q"`, `Harness(verify=[...])`, or `verify:` in Skill YAML)—blocking completion and feeding compact compiler/test diagnostics back for self-healing if any gate fails.

```mermaid
flowchart LR
    subgraph Client["CLI or Python SDK"]
        Headless["tether run --headless\ntether send / status / read"]
    end

    subgraph DB["SQLite State & FTS5 RAG Store (.tether/tether.db WAL)"]
        Sessions["sessions | inbox | turns | observations | chunks_fts (BM25)"]
    end

    subgraph Worker["Detached Session Worker"]
        Loop["Bounded Agent Loop"]
        Mux["Virtual CLI Multiplexer\nact(cmd, stdin?)"]
        Sandbox["Deterministic Sandbox\n(bwrap/unshare + workspace jail)"]
        Folder["Ephemeral Output Folder\n& FTS5 Chunk Indexer"]
    end

    subgraph Tools["Opt-In Capabilities"]
        Builtins["bash | web | edit | mem | skill | agent | done"]
        Custom["@tether.tool\nSDK & Skill Python Tools"]
    end

    Headless <--> DB
    DB <--> Loop
    Loop --> Mux
    Mux --> Sandbox
    Sandbox --> Builtins
    Sandbox --> Custom
    Builtins --> Folder
    Custom --> Folder
    Folder --> DB
    Folder --> Loop
```

### 2. Headless-First Sessions & Live SQLite Inbox
Every Tether execution is a stateful session persisted in `.tether/tether.db` (SQLite WAL mode). You can run sessions inline or spawn detached background workers (`--headless`):
- **Live Inbox & Auto-Resume:** Calling `tether send <session_id> "new instruction"` checks the session state in SQLite:
  - If **`RUNNING`**: queues the message into the session's SQLite inbox, which the worker injects before the next reasoning step.
  - If **`WAITING_INPUT` / `COMPLETED` / `IDLE`**: appends the message and automatically spawns a worker to resume the session with its pinned memory and folded context intact.

### 3. Progressive Skills (`skills/`)
Skills are portable capability bundles stored in `./skills/<name>/SKILL.md` (or `./skills/<name>.md`) with YAML frontmatter (including optional `verify` gates) and an optional sibling `tools.py`:
```markdown
---
name: researcher
description: Deep web research and synthesis specialist
model: ollama/qwen3.5:9b
tools: [web, mem, done]
---
You are a focused research agent. Search multiple sources via `web search`,
fetch key articles with `web fetch`, pin verified facts with `mem pin`,
and conclude with `act("done", stdin="<markdown report>")`.
```

### 4. Async Multi-Agent Orchestration, Deterministic Pipelines & Zero-Bloat SQLite FTS5 RAG
Because every Tether session is headless-capable, a parent agent can delegate context-heavy subtasks to child agents—or execute a deterministic multi-stage YAML pipeline—with isolated context windows **without drowning when reading results back**:
- `agent spawn --skill researcher "Summarize AI news"` $\rightarrow$ immediately returns `ses_9a2f1c` (non-blocking).
- `agent wait ses_9a2f1c ses_4b8e0d` $\rightarrow$ returns a **compact ~50-token digest** (status, chunk count, preview) rather than dumping thousands of tokens into the parent's prompt.
- `agent query ses_9a2f1c "open-weight benchmarks" --top 3` $\rightarrow$ uses **SQLite FTS5 (BM25 ranking)** over the sub-agent's chunked final deliverable *and* raw scraped observations to retrieve only the top-K relevant snippets (~250 tokens). Pass `--all` to search across all child/sibling sessions at once!
- `tether pipeline workflow.yaml "Build feature X"` (or `await harness.run_pipeline(...)`) $\rightarrow$ runs a declarative multi-stage DAG (`spec` $\rightarrow$ `implement` $\rightarrow$ `security_audit`) with **heterogeneous model routing** (e.g., frontier planner + local 9B executor), isolated per-stage `SessionRecord`s, monotonic sandbox attenuation, and compact ~50-token FTS5 stage handoffs.
- `mem search "rate limits"` $\rightarrow$ uses the same FTS5 index inside a single session to pull specific chunks from folded observations without recalling the entire raw output, or pass `mem search --project "<query>"` (and `mem pin --project <k> <v>`) to query across workspace-level facts (`__project__`) and all past `COMPLETED` sessions.

### 5. Deterministic Security Sandbox (Never Relying on the LLM)
In line with Maia et al. (2026), safety boundaries are enforced **deterministically by the harness and OS kernel**, never by prompting the model to "be careful":
- **Default `workspace-write` Jail:** Every `edit` and `bash` path is canonicalized (`realpath`) and confined to the workspace root. Sensitive paths (`.env*`, `.git/config`, `.git/hooks`, `~/.ssh`, `.tether/`) are deterministically blocked from mutation or exfiltration.
- **OS-Level Kernel Sandbox for `bash`:** On Linux, Tether automatically wraps shell commands in **`bwrap` (Bubblewrap) / `unshare`** when available—mounting `/` read-only, hiding `$HOME` with an empty tmpfs, binding only the workspace directory (with `.env*`, `.tether/`, `.git/config` and `.git/hooks` masked at the mount level), and setting `PR_SET_NO_NEW_PRIVS`. When kernel sandboxing is unavailable, Tether enforces a strict deterministic binary allowlist/denylist.
- **Secret Environment Scrubbing & Resource Caps:** Subprocesses run with a scrubbed environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_*` stripped), hard process-group timeouts (`SIGKILL`), and output byte caps.
- **Privilege Attenuation:** Child sub-agents spawned via `agent spawn` strictly inherit (or narrow) their parent session's sandbox profile and can never escalate permissions.

### 6. Multi-Model, Zero-Bloat Adapters
Tether supports any local or cloud model through **3 ultra-thin `httpx` adapters** (<200 LOC total, zero heavy SDK dependencies):
- **`ollama/<model>`** — Native Ollama `/api/chat` adapter with `num_ctx` and `keep_alive` control (e.g., `ollama/qwen3.5:9b`).
- **`openai/<model>`** — OpenAI-compatible `/v1/chat/completions` adapter (OpenAI, OpenRouter, vLLM, llama.cpp, Groq, DeepSeek).
- **`anthropic/<model>`** — Native Anthropic `/v1/messages` adapter for Claude models.

---

## Real-World Benchmark: Autonomous YouTube Short Production

To measure how harness architecture impacts token consumption, latency, and local-model viability, we ran a head-to-head benchmark across **three configurations** (2 trials each) on a multi-stage media task:

> **Task:** *"Create a 30-to-40 second vertical YouTube Short (1080x1920 `.mp4`) explaining 'What is an AI Harness, the Context Bloat Problem, and Micro-Harnesses', complete with 4 animated **Manim** vector diagrams, **EdgeTTS** neural voiceover (`en-US-ChristopherNeural`), synchronized subtitles, and **FFmpeg** muxing."*

### Results Summary (2-Trial Averages)

| Configuration | Harness | Model | Avg Steps | Avg Total Tokens | Peak Context | Avg Wall Time | Token Reduction vs. Claude Code |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Tether + Local 8B** | **Tether `v0`** | `ollama/gemma4:e4b` | **2.0** | **3,073** | **1,854** | **53.1s** | **68.8× fewer tokens** (\$0 local) |
| **Tether + Claude** | **Tether `v0`** | `anthropic/claude-sonnet-5-5` | **2.0** | **5,318** | **3,118** | **48.7s** | **39.7× fewer tokens** (2.0× faster) |
| **Claude Code CLI** | Claude Code | `claude-sonnet-5-5` | 5.0 | 211,355 | 42,091 | 97.4s | 1.0× (baseline) |

```mermaid
xychart-beta
    title "Total Tokens Consumed per Video (Lower is Better)"
    x-axis ["Tether + gemma4:e4b (Local)", "Tether + Claude Sonnet", "Claude Code CLI (Sonnet)"]
    y-axis "Total Tokens (Prompt + Output)" 0 --> 220000
    bar [3073, 5318, 211355]
```

```mermaid
xychart-beta
    title "End-to-End Wall-Clock Time in Seconds (Lower is Better)"
    x-axis ["Tether + Claude Sonnet", "Tether + gemma4:e4b (Local)", "Claude Code CLI (Sonnet)"]
    y-axis "Seconds (incl. Manim + EdgeTTS + FFmpeg)" 0 --> 110
    bar [48.7, 53.1, 97.4]
```

### Why the 40×–69× Token Difference?
1. **Zero Tool Schema Bloat:** Claude Code injects **~41,000+ tokens** of system instructions and JSON tool schemas on *every single reasoning turn* (consuming `164k–257k` cumulative tokens across 4–6 turns of file exploration and shell execution). Tether's static prefix + `shorts-maker` skill framing is **< 400 tokens**, allowing both `claude-sonnet-5-5` and a local `8B` model (`gemma4:e4b`) to one-shot the entire 4-scene YAML specification via `act("render-short ...", stdin="...")` on Turn 1 and call `done` on Turn 2.
2. **Identical Frontier Model, 39.7× Less Context:** Running the *exact same* `claude-sonnet-5-5` model inside Tether instead of Claude Code cut token consumption from **211,355 $\rightarrow$ 5,318 tokens** and halved execution time (**97.4s $\rightarrow$ 48.7s**), because nearly 100% of wall-clock time went to actual Manim + EdgeTTS rendering (~43s) rather than re-processing massive prompt prefixes.

---

## Field Notes: Tether on Small Local Models

We put Tether through two real tasks with local models, scoring the results with deterministic checks instead of impressions. The runnable example lives in [`examples/course/`](examples/course/), and the [Troubleshooting](docs/troubleshooting.md) page lists the quirks we hit and their workarounds.

### What it can do

**A free 9B model built a course.** The task: a Portuguese software-architecture mini-course (at most 3 modules, free YouTube videos, a preferred channel) produced by a plan, search, write [pipeline](docs/tutorial/workflows-and-telemetry.md). With `qwen3.5:9b` running locally, the model designed 3 modules and 15 topics on its own, and **all 15 video links were verified to be real**. Verify gates stopped every invented link and every missing topic before a stage could finish, so no fake link ever reached the output.

**A local coder fixed real bugs; a frontier model sailed through.** A small FastAPI project with a planted pagination bug, a planted code smell, and a feature request (`GET /items/search`). Each task ran 3 times on Tether v0.1.3:

| Model | Fix the bug | Find the smell | Add the endpoint |
|---|---|---|---|
| `qwen3-coder:30b` (local) | 2/3 | 3/3 | 0/3 unaided; 2/3 working code with a one-line route-order hint |
| `claude-sonnet-5-5` (through a `claude -p` provider with Claude's own tools disabled) | 3/3 | 3/3 | 3/3, finishing with `done` in 5-7 steps |

Tether ran both through the same sandboxed `bash`/`edit` tools, the same gates and the same SQLite trace. Swapping the model was a provider change, nothing else.

### What made small models work

- **The model judges, code checks facts.** Let the model design the plan and choose between options; let tools copy exact values and gates verify them. A tool that lists numbered candidates and a `yt-save <n>` that copies the URL removed a whole class of mistakes.
- **Messages are prompts.** Gate and tool errors that say what to do next (and refuse bad input with the valid options) let small models recover on their own.
- **Small stages and compact views.** One module per stage, one joined view right before a write, tool output that ends with the exact next call, and in-place swaps instead of drop-then-save kept 4B-9B models on track.
- **The trace makes it debuggable.** Every turn, tool call and gate result is in SQLite, so each failure we saw could be traced to a cause and fixed. The first round of runs exposed two harness-side problems (quoting in the `bash` tool, and how past actions were replayed to the model); both were fixed in v0.1.3, and the same bug-fix task went from 0 of 5 to 2 of 3 with the same local model.

### Where small models still need help (and how to give it)

- **Non-obvious framework gotchas.** The unaided 30B model put the new route after `/items/{item_id}` every time and could not work out why its tests returned 422. One sentence of guidance fixed it in 2 of 3 runs, and a stronger model needed no hint. Route those steps to a stronger model with per-stage `model:`, or put the gotcha in the skill.
- **Knowing when it is done.** Tether asks for an explicit `done` and caps steps; weaker models sometimes finish the work and keep tinkering, leaving backup files behind. Gates, a step budget sized to the work, and a short "when the tests pass, call `done`" line in the skill are the levers to reach for first.
- **Edits that need to be exact.** Whole-file rewrites and wrong line numbers are the usual failure. Prefer `edit replace` with a viewed range, atomic tools, and a verify gate that runs the tests.
- **Sample size.** Three runs per cell on a tiny project are a strong signal, not a benchmark. The pattern held across both experiments: the shape of the harness mattered as much as the model.

## Quickstart

### Installation (PyPI)

Tether is published on PyPI as **[`tether-sdk`](https://pypi.org/project/tether-sdk/)** (requires Python `3.12+`). Installing `tether-sdk` provides both the **`tether` CLI entrypoint** and the **`tether` Python package** (`from tether import Harness, tool`):

```bash
# Install with pip
pip install tether-sdk

# Or add to a project with uv
uv add tether-sdk

# Or install the `tether` CLI globally as an isolated tool
uv tool install tether-sdk

# Or run the CLI directly without installing
uvx --from tether-sdk tether "Explain the CAP theorem in 3 bullet points"
```

Full documentation, tutorials, and API reference: **[https://igormcsouza.github.io/tether/](https://igormcsouza.github.io/tether/)**

### Headless CLI Usage

```bash
# 1. Start a headless background session with the 'researcher' skill
$ tether run --headless --skill researcher "What are the latest news about AI?"
ses_8f92a1

# 2. Or start with explicit opt-in tools and any model
$ tether run --headless --model ollama/qwen3.5:9b --tools web,mem "Compare vLLM vs Ollama"
ses_3c71b9

# 3. Check live session status, step count, and token budget
$ tether status ses_8f92a1
ID          STATUS     MODEL              STEP   CTX_TOKENS   LAST_CMD
ses_8f92a1  RUNNING    ollama/qwen3.5:9b  3/15   580/8192     web search "AI news 2026"

# 4. Read the final report (or --steps to inspect the work log)
$ tether read ses_8f92a1

# 5. Send a follow-up (queues into live inbox if RUNNING, or auto-resumes if COMPLETED)
$ tether send ses_8f92a1 --headless "Now spawn a sub-agent to fact-check the top 2 announcements."

# 6. Inspect model pass rates, cumulative token economy, and ACI friction offenders
$ tether stats

# 7. Post-mortem: distill friction into <=2 short rules (diff; --apply writes ## Learned Rules)
$ tether retro ses_8f92a1 [--apply]
```

### Python SDK Usage

```python
import asyncio
from tether import Harness, tool


@tool(name="crm", description="Query or update customer subscription tiers")
async def crm(customer_id: int, tier: str = "pro") -> str:
    """Update customer tier. Allowed tiers: free, pro, enterprise."""
    return f"Customer #{customer_id} updated to {tier}."


async def main():
    # Minimal by default: only loads `done` + explicitly requested tools
    harness = Harness(
        model="ollama/qwen3.5:9b",
        tools=["mem", crm],
        fold_observations_after=2,
    )

    session = await harness.run(
        "Upgrade customer 1042 to enterprise, pin the audit note, and finish."
    )
    print(f"Session {session.id} [{session.status}]:\n{session.result}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Custom SDK Provider Routing (`register_provider` / `provider=...`)

Want to route Tether through a custom transport—such as an internal corporate gateway, a custom local inference server, or a mock/replay harness for testing? Implement the 1-method `ModelProvider` protocol or register a custom URL prefix with `register_provider`:

```python
import httpx
from tether import (
    Harness,
    ModelResponse,
    extract_fallback_action,
    register_provider,
)


class CustomGatewayProvider:
    """Routes Tether turns through a custom internal LLM gateway."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def generate(self, messages: list[dict], tools: list[dict]) -> ModelResponse:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://llm-gateway.internal/v1/generate",
                json={"model": self.model_name, "messages": messages, "tools": tools},
            )
            data = resp.json()
        text = str(data.get("text") or "").strip()
        return ModelResponse(
            content=text,
            action=extract_fallback_action(text),
            prompt_tokens=int(data.get("total_tokens") or 0),
        )


# Register as a custom `<prefix>/<model>` for Harness, Skills, and Sub-Agents:
register_provider("gateway", CustomGatewayProvider)

harness = Harness(model="gateway/qwen-enterprise-32b", tools=["web", "mem"])
```

---

## Built-In Virtual CLI Toolbox (Opt-In)

| Namespace | Subcommands | Description |
| :--- | :--- | :--- |
| **`done`** *(always on)* | `done [--ask] [summary]` *(or via `stdin`)* | Explicitly complete the current task (or pass `--ask` to pause in `WAITING_INPUT` and ask a question) |
| **`web`** | `web search <query>` \| `web fetch <url>` | Zero-config DuckDuckGo Lite search (auto-upgrades to Brave/Tavily/SearXNG) + clean reader |
| **`bash`** | `bash <command>` *(or script via `stdin`)* | Kernel-sandboxed (`bwrap`/`unshare`), env-scrubbed, workspace-bounded shell execution |
| **`edit`** | `edit view <path>` \| `edit write <path>` \| `edit replace <path>` | Workspace-jailed, line-numbered file viewing and `stdin`-based creation/replacement |
| **`mem`** | `mem pin [--project] <k> <v>` \| `mem search [--project] <q>` \| `mem recall <obs_id>` | Pinned session/project memory + BM25 RAG search across folded observations and completed sessions |
| **`skill`** | `skill list` \| `skill load <name>` | Progressive discovery and JIT loading of skill instructions & tools |
| **`agent`** | `agent spawn` \| `agent wait` \| `agent query` \| `agent read` \| `agent send` | Async sub-agent spawning, compact wait digests, and BM25 RAG queries over child sessions |

---

## Project Structure

```text
tether/
├── README.md
├── AGENTS.md                  # Authoritative blueprint for coding agents & contributors
├── mkdocs.yml                 # MkDocs Material documentation configuration
├── pyproject.toml             # Managed with uv (httpx, pyyaml, standard library)
├── docs/                      # Full documentation, tutorials & API reference
├── skills/                    # Built-in & workspace progressive skills
├── tether/
│   ├── __init__.py            # SDK exports: Harness, Session, Skill, SandboxPolicy, tool
│   ├── cli.py                 # `tether` CLI entrypoint (run, status, read, send, list)
│   ├── harness.py             # Control Plane: bounded agent loop, inbox polling, worker spawn
│   ├── store.py               # State & RAG Plane: SQLite WAL + FTS5 BM25 chunk store
│   ├── sandbox.py             # Security Plane: bwrap/unshare kernel sandbox & workspace jail
│   ├── multiplexer.py         # Action Plane: `act(cmd, stdin)` parser, router & JIT --help
│   ├── decorator.py           # `@tool` introspection -> POSIX CLI parser & compact usage
│   ├── context.py             # State Plane: ContextAssembler & Ephemeral Observation Folder
│   ├── skills.py              # Markdown + YAML frontmatter + companion `tools.py` loader
│   ├── providers/             # Thin httpx adapters: ollama.py, openai.py, anthropic.py
│   └── tools/                 # Opt-in built-ins: bash.py, web.py, edit.py, mem.py, agent.py
└── tests/                     # Per-module unit tests + integration suite (100% coverage)
```

---

## References

1. **Maia, P. H. M., et al. (2026).** *LLM-Native Applications as a Paradigm for AI-Driven Software Architecture*.
2. **Wang, X., Chen, Y., Yuan, L., Zhang, Y., Li, Y., Peng, H., & Ji, H. (2024).** *Executable Code Actions Elicit Better LLM Agents (CodeAct)*. In **Proceedings of the 41st International Conference on Machine Learning (ICML 2024)**. [arXiv:2402.01030](https://arxiv.org/abs/2402.01030)
3. **Yang, J., Jimenez, C. E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K., & Press, O. (2024).** *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering*. In **Advances in Neural Information Processing Systems (NeurIPS 2024)**. [arXiv:2405.15793](https://arxiv.org/abs/2405.15793)
4. **Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., & Gonzalez, J. E. (2023).** *MemGPT: Towards LLMs as Operating Systems*. [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)
