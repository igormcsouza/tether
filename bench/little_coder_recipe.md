# little-coder headless recipe (lc-1, attempt 2)

Target: little-coder v1.20.0 (package.json `version`), bundled pi `@earendil-works/pi-coding-agent@^0.83.0`, Ollama at `http://localhost:11435`, model `qwen3.5:9b`, 16384-token context.

Status: research only. Nothing was installed or run here. Every command below is copied from the upstream README, docs or source, with the URL beside it. Anything not confirmed is marked **not confirmed**.

Upstream repo: https://github.com/itayinbarr/little-coder

## 1. Install

Runtime: Node.js `>= 22.19.0`. Source: https://raw.githubusercontent.com/itayinbarr/little-coder/main/package.json (`engines`).

Project-local install (no global npm, no sudo). The README's developer path is `git clone` + `npm install`. Its `npm link` step is global, so skip it. Source: https://github.com/itayinbarr/little-coder/blob/main/README.md ("Developing little-coder locally").

```bash
git clone https://github.com/itayinbarr/little-coder.git bench/.little-coder
cd bench/.little-coder
npm install
```

- The launcher is `bin/little-coder.mjs` (package.json `bin`), so run it as `node bin/little-coder.mjs` with no global shim.
- The launcher finds pi under the local `node_modules` (`bin/little-coder.mjs`), so the local clone is enough.
- Plain `npm install` is what the README says. **Not confirmed** whether Playwright's postinstall downloads a browser outside the project (it is a declared dependency).
- The upstream one-line installer (`install.sh`, https://raw.githubusercontent.com/itayinbarr/little-coder/main/install.sh) runs `npm install -g little-coder`. Do not use it: it changes global state.

## 2. Run headless on one directory

Model override. The shipped `models.json` registers only `ollama/qwen3.5` (contextWindow 32768), with `baseUrl` `http://127.0.0.1:11434/v1` and `apiKey` set to the env var name `OLLAMA_API_KEY` (https://raw.githubusercontent.com/itayinbarr/little-coder/main/models.json). A user file replaces a provider key in full. Its path is set by `LITTLE_CODER_MODELS_FILE`, `$XDG_CONFIG_HOME/little-coder/models.json`, or `~/.config/little-coder/models.json`, in that order (README "Configuring models").

Write `bench/.little-coder/models.ollama.json`, following the shipped shape (not checked line by line; see section 5):

```json
{
  "providers": {
    "ollama": {
      "api": "openai-completions",
      "baseUrl": "http://localhost:11435/v1",
      "apiKey": "OLLAMA_API_KEY",
      "models": [
        { "id": "qwen3.5:9b", "contextWindow": 16384 }
      ]
    }
  }
}
```

Environment (all names confirmed in the source or README):

```bash
export LITTLE_CODER_MODELS_FILE="$PWD/bench/.little-coder/models.ollama.json"  # bin/little-coder.mjs, README
export PI_CODING_AGENT_DIR="$PWD/bench/.little-coder/pi-agent"                # bin/little-coder.mjs: default ~/.pi/agent
export OLLAMA_API_KEY=noop                                                    # README "Local provider keys"
export LITTLE_CODER_PERMISSION_MODE=accept-all                                # README "Permissions"; benchmarks/aider_polyglot.py
export LITTLE_CODER_MAX_TURNS=40                                              # .pi/extensions/turn-cap/index.ts
export PI_SKIP_VERSION_CHECK=1                                                # bin/little-coder.mjs (set only if unset)
```

Run one task. The launcher forwards its arguments to pi unchanged except for four flags it strips (`--no-update-check`, `--update`, `--with-pi-extensions`, `--plan-mode`). Print mode is `-p`, and a trailing prompt is passed through (https://raw.githubusercontent.com/itayinbarr/little-coder/main/bin/little-coder.mjs; README "Run" shows `little-coder --model openai/gpt-4o-mini "What does this codebase do?"` and `little-coder -p --plan-mode "<task>"`):

```bash
cd /path/to/exercise
timeout 900 node /abs/path/to/bench/.little-coder/bin/little-coder.mjs \
  --no-update-check -p --no-session --model ollama/qwen3.5:9b \
  "Implement the exercise in solution.py so its tests pass. Do not edit the test files."
```

- `-p` / `--print`: run the prompt once, write the final text to stdout, exit (https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/cli.md).
- `--no-session`: ephemeral run (https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/sessions.md).
- `--model` takes `provider/id` with an optional `:<thinking>` suffix (cli.md). See section 5 for the `:9b` risk.
- Working directory: the launcher spawns pi with `cwd: process.cwd()`, so the shell's cwd is the workspace (`bin/little-coder.mjs`).
- Wall clock: no built-in flag. `timeout 900` is the coreutils wrapper, not an upstream feature; exit 124 means it fired. The upstream runner uses a 900 s limit in Python (`prompt_and_collect(..., timeout=900)`, https://raw.githubusercontent.com/itayinbarr/little-coder/main/benchmarks/aider_polyglot.py).
- Max turns: `LITTLE_CODER_MAX_TURNS` (unset or ≤0 means no cap). At turn N+1 the extension calls `ctx.abort()` (https://raw.githubusercontent.com/itayinbarr/little-coder/main/.pi/extensions/turn-cap/index.ts). No separate steps flag exists.

Alternative proven by the upstream benchmark (not run here): `rpc_client.py` starts `node_modules/.bin/pi --mode rpc --no-session --model <model>` with `-e <index.ts>` per bundled extension, sends a JSON `{"type":"prompt","message":...}` on stdin, and waits for an `agent_end` event (https://raw.githubusercontent.com/itayinbarr/little-coder/main/benchmarks/rpc_client.py). Use this if the print form misbehaves.

## 3. Workspace footprint, finish and fail

Inside the exercise directory:

- Edits the files it is asked to change (`read`, `write`, `edit`, `bash`) (README "Run"; launcher `cwd`).
- Reads the project `AGENTS.md` or `CLAUDE.md`, capped at 4000 characters by default (README "Your project's AGENTS.md", which lists `LITTLE_CODER_PROJECT_CONTEXT=0|off|false` to disable it and `LITTLE_CODER_PROJECT_CONTEXT_MAX_CHARS`). **Not confirmed**: the exact lookup rule (whether it walks up to a parent repo).
- Writes `.pi/approved-plan.md` only in plan mode (README "Planning in a batch job").
- Does not load project `.pi/extensions/` (the launcher passes `--no-extensions`, `bin/little-coder.mjs`).

Outside the workspace:

- Session transcript unless `--no-session`: `~/.pi/agent/sessions/` (sessions.md). Move it with `--session-dir` or `PI_CODING_AGENT_SESSION_DIR`.
- `$PI_CODING_AGENT_DIR/settings.json` (set to `quietStartup: true`) and the keybinding cleanup (`bin/little-coder.mjs`). Setting `PI_CODING_AGENT_DIR` as in section 2 keeps these in `bench/.little-coder/`.
- **Not confirmed**: where the `checkpoint` extension stores its pre-edit snapshots (the extension exists, `.pi/extensions/`).

Finished or failed:

- Print mode: stderr gets errors; a final response with stop reason `error` or `aborted` exits nonzero; a response cut at the output-token limit (`length`) prints partial text, warns on stderr, and exits nonzero (https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/cli-integration.md). The numeric codes are **not documented**, so treat any nonzero as failure.
- **Not confirmed**: whether the turn-cap `ctx.abort()` yields an `aborted` stop reason (and so a nonzero exit).
- Upstream's own runner ignores the exit code and grades only by the test run (`return r.returncode == 0, ...` in `benchmarks/aider_polyglot.py`). Do the same here: the exercise's tests decide pass or fail.

## 4. Mechanisms relevant to small local models

Source: the `.pi/extensions/` listing (https://github.com/itayinbarr/little-coder/tree/main/.pi/extensions) and README "Architecture" (https://github.com/itayinbarr/little-coder/blob/main/README.md).

- `write-guard`: refuses `write` to an existing file and returns an Edit recipe; refuses truncating shell redirects to existing files (`.pi/extensions/write-guard/index.ts`).
- `read-guard-edit`: `edit` refuses until the file has been read this session (README "Architecture").
- `read-guard`: trims a Read that would overflow the window to its first 30 lines plus a search directive (README "Architecture").
- `output-parser`: repairs malformed tool calls written as fenced text, `<tool_call>` tags or bare JSON (README "Architecture").
- `quality-monitor`: empty, hallucinated or looping responses get a correction follow-up (README "Architecture").
- `thinking-budget`: caps thinking tokens per turn and retries with thinking off (README "Architecture").
- `skill-inject`: per-turn tool-skill card, chosen by error recovery, then recency, then intent (README "Architecture").
- `context-watchdog`: compacts mid-run at 80% of the window at each turn boundary; `LITTLE_CODER_COMPACT_AT_PERCENT` tunes it, `LITTLE_CODER_NO_COMPACT_WATCHDOG=1` disables it (README "Troubleshooting").
- `evidence-compact`: keeps evidence across pi's auto-compaction (README "Architecture").
- `permission-gate`: `LITTLE_CODER_PERMISSION_MODE` = `auto` (default), `accept-all`, or `manual` (README "Permissions").
- `turn-cap`: `LITTLE_CODER_MAX_TURNS` aborts at a turn boundary (`.pi/extensions/turn-cap/index.ts`).
- Launcher: `--no-context-files` and `--no-extensions` always, so only the bundled extensions load (`bin/little-coder.mjs`).
- `benchmark-profiles`: per-benchmark overrides selected by `LITTLE_CODER_BENCHMARK`, which `rpc_client.py` sets (`benchmarks/rpc_client.py`). **Not confirmed**: the profile values.

Present in the listing, behaviour not checked in this run: `checkpoint`, `knowledge-inject`, `tool-gating`, `subagent`, `plan-mode`.

## 5. Open questions (not confirmed)

1. **Model id `qwen3.5:9b`.** `--model` accepts an optional `:<thinking>` suffix (cli.md). Whether `ollama/qwen3.5:9b` resolves to the id `qwen3.5:9b` in the override, and whether that id reaches Ollama's `/v1/chat/completions` unchanged, is **not confirmed**. Check the Ollama server log on the first run.
2. **16384 context.** `contextWindow` is little-coder's own budget for compaction. Whether pi sends `num_ctx` to Ollama over `/v1` is **not confirmed**; the upstream docs describe context sizing only for llama.cpp. The server may need `OLLAMA_CONTEXT_LENGTH` or a model built with `num_ctx=16384`.
3. **Models file shape.** The fields `id` and `models` are as shown in the shipped file's summary, not checked line by line. Open https://raw.githubusercontent.com/itayinbarr/little-coder/main/models.json to confirm before the first run.
4. **Print-mode exit codes.** Only "nonzero" is documented (section 3).
5. **Headless extension behaviour.** The launcher loads the bundled extensions in print mode, but whether `quality-monitor`, `skill-inject` and the others behave the same without a TUI is **not confirmed**.
6. **Project install.** The clone + `npm install` path is from the README; whether Playwright's postinstall writes outside the clone is **not confirmed**.
7. **Corrections to earlier drafts of this file.** `--version` is not handled by the launcher, so do not use it. `LITTLE_CODER_NO_UPDATE_CHECK` does not appear in the launcher source; use `--no-update-check` (stripped by the launcher) and `PI_SKIP_VERSION_CHECK=1` instead.

## Sources

- https://github.com/itayinbarr/little-coder (README: install, run, models, permissions, troubleshooting, architecture)
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/package.json
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/bin/little-coder.mjs
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/models.json
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/benchmarks/rpc_client.py
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/benchmarks/aider_polyglot.py
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/.pi/extensions/turn-cap/index.ts
- https://raw.githubusercontent.com/itayinbarr/little-coder/main/.pi/extensions/write-guard/index.ts
- https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/cli.md
- https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/cli-integration.md
- https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/sessions.md
