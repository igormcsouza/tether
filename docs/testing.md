# Testing: golden traces

Tether is a deterministic envelope around a random model, so a change to framing, folding,
nudges, tools or retries can silently change what the model is shown. Golden traces make that
visible without a model, a network or any judgment.

Each `tests/golden/<name>.json` is a scripted session: workspace files, stubbed network
tools, the model's recorded steps and optional `send` phases. `tests/test_golden.py` replays
it through the **real** harness, multiplexer, `edit`/`done`/`mem` tools, context assembly and
folding, and compares everything against `<name>.snap.json`: the exact messages sent at every
step, event types, token estimates, final status/result and final workspace files.

- A PR that changes nothing the model sees keeps every snapshot green. A PR that does shows a
  JSON diff to approve or reject in review.
- Intended change: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`, then review the diff.
- Record a real run: `python scripts/record_golden.py <db> <session_id> tests/golden/<name>.json --stub web`
  (trim or sanitise third-party text first).

Shipped traces: a real researcher run (web stubbed, plain-text `done` nudges), a synthetic
coding run covering the edit failure modes seen with small models, and a `done --ask` /
`send` resume, and a range ping-pong (alternating views of one file; the latest read of each range stays unfolded, older ones fold). Add one for every behaviour that must not regress.

## End-to-end scenarios (local, real processes, real ollama)

`e2e/` drives the real `tether` CLI in a throwaway workspace. A small fault-injecting proxy
(`e2e/proxy.py`) sits between tether and ollama, so a scenario can force the situation instead of
hoping a model produces it: answer `429`/`503`, trickle a never-ending body, stall, or **script the
reply** (a fixed tool call, no model). Scenarios assert on what tether sent and recorded (requests,
events, DB state, exit codes, files), so they hold for any model. Task success with a real model is
only a *soft* signal (a warning), never a gate.

```bash
TETHER_E2E=1 uv run pytest e2e                       # ollama at localhost:11435 by default
TETHER_E2E_OLLAMA=http://localhost:11434 TETHER_E2E_MODELS=qwen3.5:9b,gemma4:e4b uv run pytest e2e
```

It is local only (needs ollama, never runs in CI) and skips itself when `TETHER_E2E` is unset or
ollama does not answer. A scenario tagged *model* runs once per model in `TETHER_E2E_MODELS`;
*scripted* ones do not use the model at all, so they take a second.

| Feature / bug | Scenario | Kind |
|---|---|---|
| Zero optional tools by default, single `act` schema (Rule 2) | `test_defaults::no_optional_tools_by_default` | model |
| One short index line per enabled tool (Rule 4) | `enabled_tools_are_one_short_line_each` | model |
| Static prefix, KV-cache immutability (Rule 1) | `prefix_is_immutable_across_steps` | model |
| Static framing within the token budget (Rule 1/4) | `static_framing_fits_the_token_budget` (ollama's own `prompt_eval_count`) | model |
| Disabled built-in teaches how to enable it; JIT `--help` (Rule 4) | `disabled_builtin_tool_error...`, `missing_args_return_compact_help` | scripted |
| `done`, `done --ask` + `send`, exit codes 0/2/3/4/5 | `test_lifecycle` | scripted |
| `max_steps` is an absolute ceiling, resume never overshoots (#75) | `max_steps_exit_4_and_resume...` | scripted |
| Verify gates: fail + circuit breaker, broken gate = `gate_error` (#33), pass | `gate_*`, `broken_gate_*`, `passing_gate_*` | scripted |
| `--output-schema` rejects then accepts | `output_schema_rejects_then_accepts` | scripted |
| Headless run / wait / read / status | `headless_run_wait_read_status` | scripted |
| `429` retried, honoring `Retry-After` (#98) | `test_faults::429_is_retried...` | model |
| Persistent 5xx fails loudly, exit 5 (#70) | `persistent_5xx_fails_loudly...` | scripted |
| Trickling response hits the per-attempt deadline (#88) | `trickling_response_hits_the_per_attempt_deadline` | scripted |
| Auth error names the variable, never the value (#71) | `auth_error_names_the_variable...` | scripted |
| Killed worker reported `FAILED`, not `RUNNING` (#85) | `killed_worker_is_reported_failed...` | scripted |
| Sandbox: no writes outside the workspace, protected files, env scrub, SSRF guard, read-only profile (Rule 6) | `test_sandbox` | scripted |
| Heredoc in `cmd` becomes `stdin` (#97), bare shell command redirected to `bash`, `$`/backtick wrappers, literal `\n` | `test_quirks` | scripted |
| Plain-text reply nudged, never completes; loop and cycle stalls (#39) | `plain_text_reply...`, `identical_repeat...`, `two_command_cycle...` | scripted |
| `.py` parse warning, SEARCH/REPLACE blocks (#100) | `lost_indentation...`, `search_replace_block...` | scripted |
| One done-nudge after a quiet stretch (#74) | `quiet_stretch_after_a_change...` | scripted |
| Folding to a recallable tombstone (Rule 5), per-range reads (#99) | `old_observations_fold...`, `two_ranges_of_one_file...` | scripted |
| `mem` pin/search; skills enable tools without touching the schema | `mem_pins_...`, `skill_enables_its_tools...` | scripted |
| Sub-agents: spawn is async, `wait` digest is compact, `read --full`, `query`, `send` resumes a finished child | `test_agents::agent_*` | scripted |
| Child sandbox never wider than its parent | `child_sandbox_is_never_wider_than_the_parent` | scripted |
| Pipelines: stages in order, upstream digest reaches the next stage, `act` stays the only schema | `pipeline_runs_stages_in_order...` | scripted |
| OpenAI and Anthropic wire formats, declared `command` provider | `test_surface::*_wire_format`, `declared_command_provider` | scripted |
| `web search` via `SEARXNG_URL`, `web fetch` (private hosts allowed explicitly) | `web_search_uses_searxng_override`, `web_fetch_reads_a_page...` | scripted |
| A skill's own `tools.py`: listed tool runs, unlisted stays unknown and warns | `skill_tools_py_runs_when_listed`, `skill_tool_not_listed...` | scripted |
| `stats` / `events` / `misses`; `retro` never edits a skill without `--apply` | `stats_events_and_misses...`, `retro_proposes_rules...` | scripted |
| MCP server over stdio runs a session | `mcp_server_runs_a_session_over_stdio` | scripted |
| `--no-network` cuts what the default allows (with a control), hard context budget trims old history (with a control) | `test_limits::*` | scripted |

**Not covered yet** (add a scenario when touching them): the `claude`/`vllm` flavours of the HTTP
providers beyond the wire format, Anthropic prompt caching, `web fetch` against the real SSRF
list beyond loopback and metadata, `tether pipeline` verify gates and per-stage model routing,
`mem pin --project` across sessions, `retro --apply`, and the real-model-only checks that need a
judge (answer quality).

**Merge gate (manual, because CI cannot run it):** before merging a PR run `TETHER_E2E=1 uv run pytest e2e`, paste the summary into the PR, and mitigate every failure: fix the code, fix a wrong scenario, or write down in the PR why it is acceptable and what follows up. No unexplained red scenario is merged.

**Rule:** a new feature or bug fix ships with a scenario here. If a model must misbehave to
trigger it, script the reply; if infrastructure must fail, add a fault to the proxy.

## Model conformance bench (developers only)

`bench/` holds nine tasks (the `focus` task checks that an exact single-file goal is not lost in a distractor-heavy repo) with hidden-test graders and three runners (Tether, a plain tool loop,
Claude Code) so the same model can be compared across harnesses and releases. It needs real
models, so it is not in CI and not in the package: use it when onboarding a model or before a
release to see friction that scripted tests cannot (the shell-wrapper, bare-command and
tool-name failures behind #109 were found this way). Anything it finds that can be scripted
becomes a unit, golden or e2e test. See `bench/README.md`.
