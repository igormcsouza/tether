# Release Notes

## v0.3.12 (2026-11-27)

### Security

- A session store inside the workspace outside `.tether/` (`TETHER_DB`, `Harness(db_path=)`) is protected like `.tether/`: masked under `bwrap`, and commands or `edit` paths naming it are refused under every jail (AD-55). A model could read, and change, its own session's turns and inbox there.

### Added

- A missing Python package (`No module named 'X'`) or a missing pip gets one `[hint]` line with a no-root install into a workspace venv (`uv venv && uv pip install X`) (AD-54). `qwen3.5:9b` spent 13 steps on `pip`, `apt-get` and `ensurepip` without it.

### Fixed

- Under Landlock, a read outside the workspace (`ls /usr/bin`) is no longer refused by the command-text rules: the kernel keeps writes in the workspace as under `bwrap`, and the secret-file rules stay on (AD-35).
- A shell loop or conditional (`for f in *.py; do ...; done`, `while`, `if`) runs through `bash` instead of answering "unknown command" for `for`.
- A repeated command after the session wrote files no longer tells the model to "write the file the task asked for": it names the files written and asks for `done` or a change to them (AD-21). `qwen3.5:9b` kept re-reading a finished file until a restart threw its work away.

## v0.3.11 (2026-11-27)

### Added

- `web fetch` reads a JSON reply by path: `web fetch <url>#info/version` (a JSON Pointer; the leading `/` is optional and `info.version` works too) (AD-53). A reply too big for one page prints an outline of its keys with their sizes and the command to open one, instead of the first 8,000 chars of one long line. A 6 MB PyPI reply cost `qwen3.5:9b` about 20 steps of `--from` guesses.

### Changed

- With `bash` off, a shell command (`curl`, `grep`, `python3`) answers that the session has no shell and points to the enabled tool that does the job (`curl` -> `web fetch`), instead of telling the model the flags that enable `bash`, which only the caller can pass. `qwen3.5:9b` retried shell commands 8 times in one web task.
- `web:fetch <url>` and other `<tool>:<verb>` forms run as `<tool> <verb>` when the tool is enabled (AD-30).
- `echo -e 'a\nb' > f` run as `edit write` (no `bash`) now writes two lines, and `echo -n` no newline; the flags were written into the file.
- When tether undoes a command that left a Python file unparsable, the `[REVERTED]` line now quotes the line the parser stopped at, so the model sees the mistake instead of retyping it (AD-24).
- The runtime trace of a failing test shows the same `self` object once instead of on every method call, so more of the calls fit (a 16-line trace that hit the 1,500-char cap became a complete 24-line one of 960 chars) (AD-24).

## v0.3.10 (2026-11-26)

### Fixed

- A command that deletes files you had before the session (for example `rm -rf data` to test an error path) no longer loses them: tether puts them back right after the command and says so, unless your goal asks to delete, move or clean up files (#350, AD-51).

### Changed

- An `ImportError` (`cannot import name`) or `has no attribute` error about one of your own modules now comes with one `[hint]` line saying where the name really is, for example inside a class, so the model fixes the import instead of debugging the import system (AD-52).
- When thinking runs past its 2,048-token budget, the retry with thinking off now gets the cut thought back, so it replies with a command instead of writing its reasoning out as text (up to ~10k chars before; 10 of 10 cut turns replied cleanly in a 5-exercise run, about 20 s faster each) (AD-29).

## v0.3.9 (2026-11-25)

### Changed

- The Ollama reply ceiling is 5,120 tokens (was 8,192): the 2,048-token thinking cap plus 3,072 for the reply, above every healthy turn measured, so a runaway tool call stops after about 2.5 minutes instead of 4 (AD-29). A tool call cut by the ceiling now counts the 5,120 tokens it used (it counted 2,048).

### Fixed

- Under the Landlock jail, a command that writes to `/tmp` now gets a one-line hint to use `$TMPDIR` or the workspace (a model retried such writes 7 times without it).

## v0.3.8 (2026-11-25)

### Changed

- A restart after the same tests keep failing now puts your files back to the best version so far, not to how they started, and a test run before any change no longer counts as a failed attempt (AD-21).

### Fixed

- Every Ollama turn now has the 8,192-token reply ceiling, including turns with thinking off and the retry after a thinking cut, so a reply that repeats itself stops after a few minutes instead of filling the context window.

## v0.3.7 (2026-11-24)

### Added

- Coding Ladder: three harder `shell` tiers (bisect by hand over version snapshots, dedupe by content, a log report script checked on unseen logs).
  `bench/ladder/run.py --max-tier` now defaults to the highest tier any task has, so tiers 7-9 run by default. qwen3.5:9b passes 7 and 8 and misses 9 (it accepts a fractional `ms`).

### Changed

- Ollama thinking is capped on its own (2,048 tokens before the reply starts) instead of thinking + reply together (2,560), so a whole-file write after normal thinking is no longer thrown away and redone (AD-29).

### Fixed

- Token counts include a thinking turn cut by its budget (Ollama reports none for it), so `tether stats` no longer hides the most expensive turns.

## v0.3.6 (2026-11-24)

### Changed

- On Ubuntu 24.04 and other kernels that block `bwrap`, tether now runs `bash` in a **Landlock** jail (Linux 5.13+, no sudo, no opt-out needed) instead of refusing write sessions. `tether doctor` passes and `tether status` shows `sandbox: landlock`. Landlock hides no secret files inside the workspace (the command-text rules still refuse them), cannot block the network (`--no-network` still needs `bwrap`), or unix-socket connects such as `docker.sock`; on kernel 6.12+ it also keeps jailed commands from signalling your other processes. See [security and sandbox](guides/advanced/security-and-sandbox.md#landlock-when-bwrap-is-blocked-ubuntu-2404) and AD-35.

## v0.3.5 (2026-11-24)

### Added

- The Coding Ladder has an opt-in **shell** kind (`--kinds shell`): six tasks of everyday terminal work (count, rename, CSV totals, find a leaked key, fix a backup script, report on logs), graded by checks on the deliverable and on the workspace after the run. See [the ladder page](benchmarks/ladder/index.md#everyday-terminal-work-shell).

### Changed

- The ladder report shows, per model, how many runs were answered (deliverable written, or the session completed) and the tokens spent on the runs that were not.

### Fixed

- A `python -c` probe that imports `unittest.mock` is no longer taken for the test command, so the auto-test after an edit runs the real tests.
- A `done, stdin="..."` typed into the command now delivers the answer, and a repeated unknown command that starts with "done" is caught by the loop guard instead of burning every step.
- A file rewritten back and forth between two versions, and a bare `echo` that only prints back after the tests went green, no longer reset the stall guard: the session ends "Finished by the harness" or by the stall path instead of at the step cap (AD-50).
- `bash backup.sh` and `bash ./x.sh` run the script through bash, so a script without an exec bit no longer fails with "command not found" or "Permission denied" (`bash -x x.sh` and `bash -n x.sh` too).

## v0.3.4 (2026-11-23)

### Documentation

- The docs site is reorganised into **Start here**, **Guides** (basic and advanced), **Concepts**, **Architecture**, **Benchmarks**, **Reference** and **Help**. Start here has four short pages with real runs: a first call, a web search and summary, Claude calling tether over MCP to review a draft, and a script written by Nemotron and checked by a `--verify` gate.
- New guides: find your way around, configure providers and models, review and debug a session, control cost and limits. Every guide now says why the feature works the way it does and what to do when it goes wrong.
- New **Concepts** pages, one per problem with research behind it: one action, progressive help, context and folding, a prefix that never changes, the deterministic envelope, loops and restarts, the repair loop around tests, thinking and sampling.
- New **Architecture** section: an overview, the decisions register (`AD-n` decisions, `OQ-n` open questions and a list of ideas that were tried and not adopted, each with its evidence), build and test habits, and a page on every model tested with its score on each Coding Ladder task. `AGENTS.md` points contributors and agents to the register and says it changes only when the product owner asks.
- **Benchmarks** has a page per benchmark: Polyglot-Python with the score of every version from the first measurement to v0.2.18, and the Coding Ladder pages.
- Troubleshooting entries link to their GitHub issues. The Reference section has an index that maps questions to pages.
- Orchestration logs (`.claude/gru/`) are no longer committed and are git-ignored; what they held that matters is in the decisions register.

### Added

- `tether models [--json]` lists every model id tether can use: the models Ollama has pulled, `providers.yaml` entries, the built-in prefixes with whether their API-key variable is set, and registered providers (#310).

### Fixed

- The e2e suite skips only the scenarios that call the model when Ollama does not answer; scripted and sandbox-only scenarios run without it (#307).
- Inside the `bwrap` jail a virtualenv found on `PATH` (for example the one `uv run` activates) under `/home` is mounted read-only whole, so `pytest`, `ruff` and other venv tools start instead of failing with "required file not found" or "No module named" (#76, #307).

### Changed

- `bench/run.py` has a `plain` runner next to `naive`: the same bare tool loop, but through Ollama's native `/api/chat` with the same `num_ctx` as the tether run (the `/v1` route ignores it) and up to three reminders to keep going when the model replies without a tool call. It makes the comparison with a bare model fairer to the local model.
- `bench/ladder/charts.py` writes its charts to `docs/benchmarks/ladder/img/`.

## v0.3.3 (2026-11-20)

### Security

- A shared `tether mcp` server refuses `allow` and `allow_unsandboxed` from `tether_run` callers unless it was started with `tether mcp --permit-widen`. Before, any caller could widen the sandbox for every later session of the workspace. MCP clients that pass either argument must now run against a server started with the flag (#306).

### Fixed

- Ctrl+C during `tether run` prints one line, exits 130 and hands the session back as `WAITING_INPUT` (resume with `tether send`); the running bash command is killed. It used to print a 70-line traceback and leave the session `RUNNING` with a dead pid (#309).
- A `--verify` gate runs under its own timeout, 300 s by default, `TETHER_GATE_TIMEOUT` seconds to change it, instead of the 30 s bash timeout. A gate that runs out says so and names the variable (#304).
- `tether doctor` and the `Sandbox unavailable` error tell `bwrap` installed but refused by the kernel (AppArmor user namespaces on Ubuntu 24.04+) from `bwrap` missing, show the kernel's message and give the fix, instead of saying to install what is installed (#311).
- With `--limit cpu`, only the kernel's cpu signal is reported as a cpu hit. A `kill -9` is no longer labeled `[limit hit: cpu ...]` because another command used CPU at the same time (#303).
- The command-provider retry test no longer fails on a loaded machine (#308).

## v0.3.2 (2026-11-20)

### Changed

- A session that runs out of steps (or is handed back stuck) gets one final answer-only model call (Ollama gets no tools, OpenAI-compatible and Anthropic get `tool_choice: none`): a plain-text or `done` reply leads the `[STUCK ...]` summary, and a command in it is not run but answered once. On the probe tasks nemotron and qwen3.5:9b now hand back their review or research answer instead of nothing. The `[LAST STEP]` notice and the 75% `steps left` notice are removed: models ignored them 4 of 4 times.
- The Qwen3 XML tool-call form written as text (`<function=act><parameter=cmd>...`) is parsed as a command.
- `tether stats` shows `notices followed:`: for each notice that asks the model to act, how often it fired and how often the next step did what it asked.
- What a command changed is found by comparing the workspace files before and after it, not by parsing the command text. `tether diff` snapshots, the `[REVERTED]` check, the unchanged-code note and the `[auto-test]` trigger all use it, so writes by `perl -pi`, scripts and any other shell form are tracked, and refused commands, no-op edits and writes outside the workspace are not changes. Workspaces over 50,000 files fall back to the old rule.

### Fixed

- A failed tool now says what happened and what to do next. `web fetch` names the HTTP status and a next step for 429, 401/403, 404/410 and 5xx, or the unreachable host; a page with no readable text is an error, not an empty reply. A tool that raises shows one `Error: <tool> failed:` line and the hint `Instead: run <tool> --help`. `web fetch` reads only the `main` or `article` element (or the role=main element) when the page has one, so site navigation no longer fills the reply.
- `edit replace --lines`, `edit append` and `edit insert` apply a stdin made of SEARCH/REPLACE blocks on an existing file, like `edit write`, instead of writing the markers into the file. nemotron corrupted a 400-line file this way while writing the model guide (#332).

### Removed

- The `[BEFORE WRITING]` question after the first read of a test file, and the notices that point to `edit replace` after a small whole-file rewrite or a near pass: on the v0.2.18 bench qwen3.5:9b followed them 0 of 68 and 1 of 50 times (#272).

### Docs

- New guide [Choose a model: what to expect](guides/basic/choose-a-model.md): what each model does through tether, where it fails, and the same five tasks run on qwen3.5:9b, nemotron, Haiku, Sonnet and Opus.

## v0.3.1 (2026-11-14)

### Added

- `edit insert <path> --line N` adds the stdin lines before line N and replaces nothing, so a small model no longer loses line N when it adds lines (#320). A bare `edit replace <path> --lines a:b` with empty stdin now says it deleted the lines (#321), and `edit append` and `insert` always end the file with a newline.

### Fixed

- A session whose only edits were refused (wrong command shape, sandbox refusal) is no longer ended as `COMPLETED` "Finished by the harness ... after its change": a refused command ran nothing, so it does not count as a change and the session is handed back as `WAITING_INPUT` (#318).
- `edit replace <path>` now applies a unified diff or bare `@@` hunks sent as stdin through the same applier as `edit <path>`; a `, stdin="..."` tail typed inside the command is moved into stdin; and `edit replace <path> --lines a:b` applies a marked `-`/`+` diff of exactly those lines, so a correct edit is no longer refused or mis-applied (#317).
- A headless worker no longer imports workspace code through a relative or empty `PYTHONPATH` entry: only absolute entries are passed on (#283).
- The sandbox no longer fails every `bash` call with `bwrap: Can't create file at /run/...` when `/run` holds a symlink to a unix socket (e.g. `/run/php/php-fpm.sock`): the socket the link points to is masked, once.
- `sed -n '45,90p file'` (the path typed inside the quotes) now runs as `sed -n '45,90p' file` instead of failing (#270).
- A `command` provider that hits a usage or rate limit now fails at once with the provider's own words and a next step (`wait for the reset or pass another --model`), instead of a raw JSON error after retries (#305).
- A `bash` command that times out after starting a background job (`server &`) now says why and what to do: run it in the foreground with `timeout N <cmd>`, or send its output away with `<cmd> >/dev/null 2>&1 &` (#319).
- `web search` now says when the search engine refuses (HTTP 202 or a bot-check page) instead of printing `No search results found.`, so a model stops retrying. `web fetch <url>#anchor` starts the returned text at that element, and `web fetch <url> --from <text>` starts it at the first match. A cut page names the `--from` words to continue with.
- The harness tells a session that only looks things up to answer, not to edit: the step before the limit gets a `[LAST STEP]` notice, the 75% and 12-step nudges ask for an answer when neither `bash` nor `edit` is enabled, and a restart or failed `verify` gate after a check failed 3 times names `done --ask` as the way out of a wrong test.
- A `bash` command that leaves a Python file unparsable is undone: the file goes back to its bytes from before the command, and the observation names it in a `[REVERTED]` line so the model redoes the change in smaller steps (F5).

### Docs

- New guide [Write tasks a small model can finish](guides/basic/write-tasks-small-models.md): the task-writing rules, a re-runnable example, what each model was seen to do well and badly, and how to tell whose fault a failed task is.

## v0.3.0 (2026-11-09)

### Breaking changes

- Without `bwrap`, a `workspace-write` session with the kernel sandbox on is now refused before the first model call (exit 1). Migration: pass `--allow-unsandboxed` (SDK `SandboxPolicy(allow_unsandboxed=True)`/`Harness(allow_unsandboxed=True)`, MCP `allow_unsandboxed`), or set `TETHER_SANDBOX=container` in Docker. With the opt-out, one `[sandbox] bwrap not available, running with command checks only` line is printed on stderr (#124 item 2).

### Changed

- Sandbox refusals now name the rule, what to do instead, and the flag that would permit it when one exists (#124 item 3). No change to which commands are allowed or refused.
- Observation folding is automatic by default: above half of `max_context_tokens`, old outputs fold oldest-first only until the history is back under that target (no cliff), and each unedited re-read lengthens K by one (cap 8). `--fold-after N` keeps the fixed rule (#205).

### Added
- Sandbox conformance suite: a table of must-run and must-refuse commands, run against the text layer and real bwrap. It proves items 1 and 9 of #124.
- Escalation: ask the caller once, then remember (#59, #124 item 4). A command whose prefix is in the policy's `escalate` list (default `git push|pull|fetch|clone|worktree|config`, `gh`, `docker`) and not allowlisted pauses the session as `WAITING_INPUT` (exit 2) with `[APPROVAL NEEDED] <command>` and the JSON key `approval`. `tether send <id> approve` (or the new `tether allow <id>`, MCP `tether_send`) adds the prefix to `.tether/allow.json`, runs the command outside the jail and resumes; any other reply refuses it. Never offered for metacharacters, unsafe git options, read-only or `--no-network` sessions.
- Allowlist of command prefixes that run outside the jail (#59, #124 item 4): `tether run --allow` (repeatable), `allow` in `.tether/allow.json`, and the MCP `tether_run` argument `allow`. Whole-token prefixes, no shell, never in read-only or `--no-network` sessions.
- Sandbox refusals are recorded as `sandbox_violation` events with their rule, and `tether stats` shows the top rules (#124).
- Opt-in resource limits for `bash` (#124 item 6): `tether run`/`pipeline --limit KEY=VALUE` (cpu, mem, fsize, procs), `SandboxPolicy(limits=)` and the MCP `tether_run` argument `limits`; off by default, Linux only, a hit adds a `[limit hit: ...]` line.
- Web domain allowlist (#124): `tether run --web-allow` (and `SandboxPolicy(web_allow=)`) restricts the `web` tool to listed domains; sub-agents and stages can only narrow it.
- `tether pipeline --web-allow` and the MCP `tether_run` argument `web_allow` set the same domain allowlist. A malformed value (spaces, a `*` outside a leading `*.`, a URL) is a usage error or a ToolError, not a silent pass.
- Docs: install with the network, work without it (`--setup`, `--no-network`) (#124).
- `tether status` shows `sandbox: bwrap` or `sandbox: command checks only`.
- `tether export <id>` prints a session as a Markdown transcript (`--out FILE` to save it).
- A `--verify` gate whose program does not exist (checked for every command in a `&&`/`||`/`;`/`|` chain) now fails the session before the first model call, as a misconfigured gate (#82).
- `tether doctor` checks your setup (Ollama reachable, model pulled, bwrap, providers.yaml, session DB) and says what to fix; exit 1 when a check fails.
- `tether run --worktree` runs the session in its own git worktree on branch `tether/<id>` and commits the result there when it stops. `--worktree-from <ref>` sets the base ref and `--setup <cmd>` runs a shell command in the worktree before the model starts (outside the sandbox, not offered over MCP). See [Run a session on its own branch](guides/advanced/own-branch.md).
- `tether read <id> --thinking` prints the stored model thinking for each step. Thinking is kept for reading only and is never replayed to the model.
- `tether replay SESSION_ID` re-runs a session's goal in the current directory with its saved tools, skill, sandbox, output_schema and params, and prints the original and replay side by side (`--model`, `--max-steps`, `--json`). Verify gates are not stored, so a replay runs without them.
- `tether pipeline --resume <id>` re-runs a failed or waiting pipeline from its first unfinished stage and reuses the stages that completed (#35).
- `--max-tokens N` (CLI), `Harness(max_tokens=)` and the MCP `tether_run` argument `max_tokens` set a token budget (prompt + completion). When the budget is reached the session pauses as WAITING_INPUT (exit 2) and `send` adds the same amount again as a grant. Sessions without a budget are unchanged.
- `tether mcp`: `tether_run` accepts `workspace`, an absolute directory inside the server's workspace, so a caller working in a git worktree can root the run there; anything outside is refused (#242).
- `tether diff <session_id>` shows what a session changed in its files, against the first bytes the session saw (`--stat` for line counts). Snapshots are recorded by the harness write-tracking loop in a new `file_snapshots` table; files created by the session show as added from empty.

### Fixed
- A headless worker that dies before it starts no longer leaves its session PENDING: it is marked FAILED with `Worker died (pid N) before starting`, and the result names the worker's log (`<db dir>/workers/<id>.log`), which now keeps the worker's stdout and stderr (#271).
- `edit write` on an existing file with stdin made only of complete SEARCH/REPLACE blocks now applies them as `edit replace` instead of replacing the whole file (#267).
- Replay and list columns no longer collide with long model ids or WAITING_INPUT, and `replay` accepts `--worktree`, `--worktree-from` and `--setup` (#279).
- `tether wait` exits 6 and prints `timed out; still RUNNING: ...` on stderr when the timeout expires (#269).
- Command provider timeouts and empty failures are retried twice before raising `ProviderError` (#268).
- Headless workers always import the installed tether, never a workspace's own tether/ package (#273).
- An empty model reply is retried. If the retry is empty too, the session stops instead of continuing with no output (#135).
- `tether run --worktree` no longer commits bytecode and tool caches (`__pycache__`, `*.pyc`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.tether/`) (#278).
- `tether diff` shows writes by `sed -i`, `perl -i`, `mv`, `cp`, `python -c`, and names files changed by commands it could not track instead of `no file changes recorded` (#280).
- Masked secret files and `.git/config` now read as empty instead of "Permission denied", so `git status`, `git log` and `grep -r` work inside the sandbox (#124 item 1).
## v0.2.18 (2026-11-08)

Small fixes from the v0.2.17 release check and the paasio labs: shell-style file writes work when only `edit` is enabled, `edit append` adds to a file instead of replacing it, a foreground run prints its session id at once, and a `cd` into a container path that does not exist no longer costs a step.

### Added

- `edit append <path>` adds `stdin` to the end of a file (created if missing, with a newline added when the file does not end with one). Small models assumed `edit write` appends: gemma4:e4b wrote a plan module by module and kept only the last one. The `edit` help now says `write replaces the file` and stays within 59 tokens; with `bash` off, `echo t >> f` runs as `edit append f` (#34).
- A foreground `tether run` (with or without `--json`) writes `session ses_<id>` to stderr as soon as the session is created, before the first model call. A caller that kills the run on its own timeout no longer needs `tether list` to find the id for `status`, `stop` or `send`; stdout is unchanged (#90).

### Fixed

- `cd /testbed && python3 -m unittest ...`, with a directory that does not exist, now runs the command after the `cd` in the workspace, with one line saying the `cd` was skipped. Models assume a container path; qwen3.5:9b lost a step to it in 3 of the last 6 paasio runs. A `cd` into a real directory runs as before (#79).
- `tether stats` offenders: a leading `cd <dir> &&` no longer makes `cd` the offending command (the command after it is counted), and a turn without a command shows as `(no command)` instead of `unknown` (#79).
- With `edit` enabled and `bash` not, a plain shell file write or read now runs as `edit`: `echo ok > hello.txt`, `printf 'a\nb' > f`, `cat > f << 'EOF' ... EOF` become `edit write`, and `cat f` becomes `edit view f`. Any other shell command still answers `unknown command`, now with a pointer to `edit view|write`. In the v0.2.17 release check (`--tools edit`, "Create hello.txt containing ok"), qwen3.5:9b tried `echo`, `printf`, `cat` and `ls` 10 times before writing the file at step 12 of 15. Pipes are not translated.

## v0.2.17 (2026-11-07)

When tests fail, tether now works around them on its own time: it re-runs them after each edit, traces the smallest failing test, starts fresh when an approach keeps failing, and keeps a version that nearly passes instead of throwing it away. The north star (74% on Polyglot-Python with qwen3.5:9b) moves to v0.4.0. No full Polyglot run was made for this release; the numbers below are from targeted labs.

### Added

- A repair loop around failing tests, all from the harness's own time (0 static prompt tokens, no extra model call). Once the model has run the tests, they run again after each edit and the result is appended (`[auto-test]`), so no version is typed blind. When the model reads the tests of the file it is about to write, it is asked once to say in plain words what the hardest tests call and expect (`[BEFORE WRITING]`). When the same tests fail again after a change, or only a few still fail, a runtime trace of the smallest failing test shows the calls into your code with their arguments and results. When at most 3 tests still fail, one note points to `edit replace` instead of a whole-file rewrite. On `paasio` with qwen3.5:9b (600 s cap) the mean score went from 0.63 over 3 runs to 0.94 over 5 runs, with 1 of 5 passing; the other 4 ended at the time cap with 22 to 24 of 25 tests passing (#173).

### Changed

- The north star is now 74% (50 of 68) on Polyglot-Python with qwen3.5:9b by v0.4.0, instead of 80% by v0.3.0. 74% is the share of exercises the model has already solved at least once from scratch (25 of 34), so the target is reliability: each of them passing every run. The 9 exercises it never solved are out of scope for this target (#173).
- A restart after the same tests failed 3 times is now a fresh start: the files the model changed go back to how they started, and the restart message names the failing tests instead of quoting the failed code (Olausson et al., ICLR 2024). A version that already passes all but at most 3 tests is kept instead: when later edits do not beat it, its files come back in place with a `[RESTORED]` line and the history stays (#173).
- The number of failing tests is read from the runner's summary line (`FAILED (failures=1, errors=3)`), so a test run cut by `| head` is no longer taken for a near pass (#173).

### Fixed

- `edit write hello.txt ok`, with the content typed after the path and no `stdin`, now writes `ok` instead of answering ``Error: `edit write` requires file content in `stdin` ``. qwen3.5:9b lost two steps this way creating a one-line file in the v0.2.16 smoke run. The text is taken as typed (spacing kept, one pair of surrounding quotes removed, literal `\n` unescaped); `stdin`, when given, still wins (#173).
- In `tether list`, a pipeline's own row now shows the model its stages run on instead of the harness default (`ollama/qwen3.5:9b` even when every stage set `model: local/qwen3.5:9b`). When stages use different models, the row lists them in stage order, joined with `,`. A stage with no `model:` still runs on the pipeline's default model.
- A test run piped to `head` (`python3 -m unittest ... 2>&1 | head -100`) now keeps its result. The runner prints its summary (`Ran 26 tests` / `FAILED (failures=8)`) last, so `head` cut it, and the pipe also replaced the tests' exit code with `head`'s 0: the model could not tell how many tests failed, and tether's own notes on test runs (failing test source, regressions, green-test finish) did not fire. Now tether runs the test command itself, keeps the first N lines and adds `[... K lines cut by head; the end of the output:]` with the last 6 lines and the real `[exit N]`. In the v0.2.15 Polyglot run on qwen3.5:9b, 22 of 39 failing runs had at least one test result cut this way, against 7 of 47 passing runs. On 4 of those exercises plus 2 passing controls (32k, one run each), e
... [truncated 48,068 chars by sandbox cap] ...
- **Multiplexer**: small models that send `edit write`/`edit replace` stdin or the `done` deliverable as one line with literal `\n` (and `\t`) escapes now get them unescaped deterministically (only when the stdin has no real newline). `bash` stdin and all other tools are never touched. (#26)

---

## v0.1.1 (2026-10-18)

### Fixes
- **Bash**: a command with no output now returns `[exit 0: no output] Command succeeded.` instead of a bare `[exit 0]`, which 9B models misread as failure and repeated until the loop breaker fired.
- **Docs**: new tutorial page for gates, `done --ask`, project memory, pipelines, `stats` and `retro`; added the documented-but-missing `tether --version`.

---

## v0.1.0 (2026-10-17)

### Milestone v0.1: Deterministic Control Plane
- **Pre-`done` Verification Gates**: `Harness(verify=[...])`, `--verify`, or Skill `verify:` run inside the session `SandboxPolicy` before `done` can complete a session (0 static prompt tokens until a gate fails).
- **Interruptible `WAITING_INPUT` & `done --ask`**: sessions can pause for human/parent input and resume via `tether send`.
- **Hierarchical Project Memory**: `mem pin --project` / `mem search --project` with cross-session BM25 RAG.
- **Telemetry & Failure-Mode Inspector (`tether stats`)**: per-model pass rate, token cost, step latency and ACI friction offenders.
- **Deterministic Multi-Stage Pipelines (`tether pipeline`)**: isolated stage sessions, heterogeneous model routing, monotonic sandbox attenuation, ~50-token stage handoffs.
- **Post-Mortem Distillation (`tether retro`)**: `tether retro <session_id> [--apply]` extracts a session's friction trace (inbox corrections, loop stalls, syntax/tool errors, gate failures) and distills at most 2 deduplicated rules (<= 30 tokens each) into `SKILL.md` under `## Learned Rules`, or project memory when no skill was used. Runs offline, never mutating a live prompt.

### Fixes found during release validation
- **Sandbox**: `bwrap` now really unshares PID/IPC namespaces (docs claimed it); under `bwrap`, `.env*`, `.tether/`, `.git/config` and `.git/hooks` are now masked at the kernel level. Previously only a command-string regex guarded them, so `cat .e*` or `cat $(echo .en)v` read secrets and `echo >> .git/con*` modified git config. `SSH_AUTH_SOCK`/`GPG_AGENT_INFO` are scrubbed and `/run/user` is hidden.
- **`tether stats`**: pipeline root sessions are excluded; they invented a run for the default model and double-counted stage tokens.
- **Multiplexer**: an unknown first token (e.g. a raw `echo hi > f`) now hints `bash <cmd>` when the `bash` tool is enabled; small models previously looped on the bare error.
- **CLI**: `tether pipeline` (missing file, invalid YAML, stage without `goal`) and `tether send <unknown id>` print `Error: ...` and exit 1 instead of a traceback.

---

## v0.0.3 (2026-10-17)

### Architectural & Performance Upgrades
- **Head + Tail L1 Active Observation Elision (`tether/context.py`)**: Oversized active observations (`> 2,400 chars`) are deterministically elided in L1 working memory to their first 900 chars (headers/command summary) + last 900 chars (stack trace/exit code) with a pointer to `mem recall` / `mem search`, preserving full outputs in SQLite FTS5.
- **Deterministic Loop-Stall Breaker (`tether/harness.py`)**: Consecutive identical `(cmd, stdin)` calls from small 8B/9B models are intercepted before tool execution and answered with a deterministic `[LOOP DETECTED]` recovery nudge.
- **100% KV-Cache Prefix Immutability Across Pins (`tether/context.py`, `tether/providers/anthropic.py`)**: `[PINNED MEMORY]` is attached to the tail message after window trimming so earlier turn messages remain 100% byte-identical when pins change; added Anthropic ephemeral `cache_control` breakpoints.
- **Persistent Connection Pooling & Thread-Local SQLite WAL (`tether/providers/*`, `tether/store.py`)**: Reuses persistent `httpx.AsyncClient` instances across turns and caches thread-local SQLite WAL connections with `PRAGMA temp_store=MEMORY;` and 128 MB `mmap_size`.

### Packaging, Documentation & CI
- **PyPI Trusted Publishing (`tether-sdk`)**: Published on PyPI as `tether-sdk` (`pip install tether-sdk` / `uv add tether-sdk`) with automated OIDC delivery (`.github/workflows/delivery.yml`).
- **Flattened Package Layout**: Moved `tether/` to the repository root (removing `src/`).
- **MkDocs Documentation Site**: Added full documentation, tutorials, literature review, and `mkdocstrings` API reference at `https://igormcsouza.github.io/tether/` (`.github/workflows/docs.yml`).
- **Modular Test Suite & 100% Coverage CI Gate**: Split unit tests into 20 per-module test files under `tests/` and added `.github/workflows/ci.yml` enforcing `ruff`, `mypy`, `mkdocs build --strict`, and `pytest --cov=tether --cov-fail-under=100`.

---

## v0.0.2 (2026-10-17)

### SDK Provider Extensibility & Literature Grounding
- **Custom SDK Provider Registry (`register_provider`)**: Added `register_provider(prefix, factory)` in `tether.providers` so SDK consumers can route `<prefix>/<model>` identifiers through custom gateways, local inference engines, or test transports.
- **Literature Grounding**: Documented architectural alignment with Maia et al. (2026), Wang et al. (*CodeAct*, ICML 2024), Yang et al. (*SWE-agent*, NeurIPS 2024), and Packer et al. (*MemGPT*, 2023).

---

## v0.0.1 (2026-10-16)

### Initial Release
- Single `act(cmd, stdin)` action multiplexer with `< 150` tokens of base framing overhead.
- `@tool` Python function introspection with JIT `--help` disclosure (`<= 60` tokens).
- SQLite WAL session store + FTS5 BM25 RAG (`chunks_fts`) and ephemeral $K$-turn observation folding.
- Detached headless worker execution (`tether run --headless`, `wait`, `send`, `query`, `read`, `list`).
- Always-async multi-agent orchestration (`agent spawn`, `wait`, `query`, `read`, `send`).
- Deterministic `SandboxPolicy` with workspace path confinement, secret environment scrubbing, and Linux `bwrap` isolation.
