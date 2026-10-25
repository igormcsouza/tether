# Guides

*For: people using tether day to day. Each guide is a job to be done; pick the one that matches yours.*

This tutorial walks through every layer of **Tether**, from running your first local 9B session in the terminal to orchestrating multi-agent workflows with custom Python tools and SQLite FTS5 retrieval.

1. **[CLI and Headless Sessions](cli-and-headless.md)** — Run foreground sessions, spawn detached background workers (`--headless`), inspect live progress (`status`, `wait`), send live follow-ups (`send`), and query results (`read`, `query`).
2. **[Python SDK and Custom Tools](sdk-and-custom-tools.md)** — Configure `Harness`, decorate Python functions with `@tool`, pass multiline payloads over `stdin`, and leverage progressive `--help` disclosure.
3. **[Built-in Tools](built-in-tools.md)** — Master the opt-in built-in namespaces: `done`, `bash`, `edit`, `web`, `mem`, and `agent`.
4. **[Progressive Skills](skills.md)** — Bundle domain instructions (`SKILL.md`) and custom Python tools (`tools.py`) into reusable skills discovered in `./skills/` or `~/.tether/skills/`.
5. **[Async Multi-Agent Orchestration](multi-agent.md)** — Spawn parallel child sessions (`agent spawn`), wait for compact 50-token digests (`agent wait`), and run sub-millisecond BM25 RAG across sub-agent observations (`agent query`).
6. **[Security and Sandbox](security-and-sandbox.md)** — Enforce deterministic path confinement, `.env`/`.git` protection, secret environment scrubbing, and Linux `bwrap` kernel isolation.
7. **[Gates, Memory, Pipelines & Telemetry](workflows-and-telemetry.md)** — Verification gates (`--verify`), `done --ask`, project memory (`mem --project`), YAML pipelines, `tether stats` and `tether retro`.
8. **[Use Tether Inside Your Harness](agent-interface.md)** — Run Tether as a subagent of Claude Code, Codex, Cursor, Gemini CLI or Copilot over MCP (`tether-sdk[mcp]`), with `--json` and exit codes for scripts.


Throughout the tutorial, the [course-builder example](https://github.com/igormcsouza/tether/tree/main/examples/course) (`examples/course/`, a three-stage pipeline that plans, researches and writes a small course with `ollama/qwen3.5:9b`) is the running example: each page shows the piece of it that illustrates that feature, plus the limits we hit. Problems are collected in [Troubleshooting](../troubleshooting.md).
