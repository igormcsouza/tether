# Work on v0.2.4
- Slug: work-on-v0-2-4
- Status: done
- Started: 2026-10-20   Updated: 2026-10-20   Closed: 2026-10-21
- Branches / PRs: worktree branch `claude/caveman-full-3e3119` (base main @ 8f0e0dd)

## Goal
Work toward Tether v0.2.4 (follows v0.2.3 release, #94). Milestone v0.2.4: #88, #85, #75, #74.

## Requests
- 2026-10-20: `/keep-feature-context new work-on-v0.2.4` — start log for v0.2.4 work.

## Decisions
- 2026-10-20: SWE = tether headless, model `nvidia/nvidia/nemotron-3-ultra-550b-a55b` (provider `nvidia` in ~/.tether/providers.yaml, key NVIDIA_API_KEY from ~/.profile). Verify gates: ruff, mypy, pytest cov 100. 3 parallel worktrees (#75+#74 share harness loop so one session).
- 2026-10-20: Session runs with caveman (full) + ponytail (full) modes; code/commits/PRs written normal.

## Problems

## Problems
- 2026-10-20: 3 parallel nemotron sessions all hit NVIDIA HTTP 429 (3 retries). Run sequentially.
- 2026-10-20: #88 ses_c488b7de resumed: 93/80 steps (max_steps overshoot = #75), 0 edits, only reads/sed. Retry ses_eee3fb0f with exact plan: 60/60 steps, FAILED, tree clean; last cmd `edit replace ... --lines 62:62` (invalid syntax guess). Nemotron-3-ultra via tether not landing edits; likely needs `edit --help` discipline or stronger model.

## Progress log
- 2026-10-20: Log created. Existing related log: `active/v0-2-bugs.md`.

- 2026-10-20: Milestone v0.2.4 = #88, #85, #75, #74 (all bugs). Launched: #88 ses_c488b7de (~/worktrees v024-88, fix/88-provider-deadline); #85 ses_b5cc20de (v024-85, fix/85-stale-running); #75+#74 ses_008272e8 (v024-75-74, fix/75-74-maxsteps-done-nudge). Worktrees under .claude/worktrees/.

- 2026-10-20 FINDINGS (dogfooding nemotron-3-ultra via tether, runs ses_c488b7de/eee3fb0f/2eaaba60/760137c4):
  1. Model NEVER used the `stdin` param (0 of 150+ turns); wrote heredocs/quoted text in `cmd` -> `edit replace` rejected 4x. FIX COMMITTED: a61b312 on branch fix/heredoc-stdin (worktree v024-88): multiplexer turns trailing heredoc in cmd into stdin (not for bash). Tests 100% cov, docs updated. After fix model did land an edit (first time).
  2. Read thrash: model cycles ollama->anthropic->openai->base->test files (period-5). `live_reads` MAX_LIVE_READS=4 < 5 files -> LRU thrash, each re-read evicts next. `detect_cycle` only catches 2-gram x3 / 3-gram x2, window 8 -> never fires. Raising active_char_cap 2400->8000 did NOT help (27/46 repeat cmds); reverted.
  3. NVIDIA free tier 429s even sequentially; `post_with_retry` retries 2x with 1s,2s backoff, no Retry-After -> sessions die FAILED (ses_760137c4 at 46/60).
  4. max_steps overshoot (93/80) after `send` resume = #75; no done nudge = #74.
  5. gh needs auth inside sandbox (GH_TOKEN env dropped) -> model cannot read issues; paste issue body into goal.
  Ideas: detect_cycle n up to 5 w/ window 12; MAX_LIVE_READS 4->8 (or scale with budget); 429 honors Retry-After + longer backoff; completion/explore-budget nudge (#74).

- 2026-10-21 PRESET SEARCH (unscoped #88, nemotron-3-ultra, harness script scratchpad/exp.sh; all FAILED, 0 reached done):
  | run | change | tokens | steps | result |
  | ctrl x2 | none | 343-423k | 60 | 0 edit-tool calls, 8-20 repeats |
  | A | skill text (bash prefix, stdin, edit flow) | 395k | 60 | no edits |
  | B | fold-after 8, ctx 32k | 368k | 60 | no edits |
  | C0/C1 | SEARCH/REPLACE edit tool (+skill) | 403k/422k | 60 | edited 3-4 files via bash patch scripts at step ~55, unfinished |
  | D | C1 + 120 steps | 784k | 101 | died on 429; still re-reading at 101 |
  | E | obs cap 8000 + fold 8 + ctx 32k + skill | 447k | 60 | 39 repeats, no edit |
  Replay of stuck step 58: model reasoning = 'now implement' but action = `cat base.py` again; echoing reasoning_content back did NOT change it (4/4 still cat). Observations fully visible (8099 chars, not elided). Knobs (fold, cap, ctx, steps, skill text) do not fix; only SCOPED goals (file+range+exact plan) produced edits (ses_8a959866).
  Committed on branch fix/88-provider-deadline (worktree v024-88), all 100% cov: heredoc->stdin; 429 Retry-After + 5 attempts; MAX_LIVE_READS 8; reads keyed by path+range; .py parse warning on edit; SEARCH/REPLACE blocks.

- 2026-10-21 #85 SCOPED BRIEF WORKS: brief = scope (file+methods), numbered plan, test spec, run cmd (scratchpad/goal85.txt, exp3.sh, skill C). ses_acb4e576: 40 steps, 214k tokens, correct `_reap_dead` + test, but hit max_steps before done. Gaps I fixed by hand: PermissionError (other-user pid = alive; my plan omitted it), test_agent_interface fake-RUNNING session needed pid=os.getpid(), release notes/AGENTS.md. Committed ef08560 on fix/85-reap-dead-worker (from main, clean for PR). Model diff saved scratchpad/nemotron-85.diff.
  Lessons: scoped brief >> any knob; brief must list edge cases/existing tests that interact; give 50% more steps than the plan needs (it burned ~12 steps on test/doc fiddling via python-heredoc rewrites).

- 2026-10-21 #88 via scoped brief: ses_b251069e, 32 steps, 126k tokens, correct first pass (wait_for + test + docs). Session FAILED only from gate_error: verify gate used `uv run` but sandbox env has no uv on PATH -> use `.venv/bin/ruff|mypy|pytest` in --verify (exp3.sh updated). Rebased onto main as fix/88-attempt-deadline, PR #101. Brief template that works: scope+files, numbered plan with exact lines/strings, indentation warning, test spec naming helpers to reuse/avoid, docs bullets, run cmd, done. Skill C (SEARCH/REPLACE hint) used.
- 2026-10-21 #74 brief (done-nudge: is_quiet() + QUIET_NUDGE_STEPS=6 one-shot [NUDGE] appended to observation) running as ses via exp3.sh F74. #75 design pending: max_steps semantic = per-run budget; `step_limit = step_start + rec.max_steps` in execute_session (harness.py ~593) is why 46/40; need display fix in status.

- 2026-10-21 MERGED (squash, order #103,#96,#98,#101,#102,#99,#97,#100). Conflicts handled: release-notes (scratchpad/rn.py re-applies each PR's bullets onto main), AGENTS.md + tests appended by two PRs (kept both), golden snapshot drift on #97 and #100 reviewed + accepted (intended: heredoc step ok; parse warning/SEARCH-REPLACE). Gotcha: PR #97 head stuck stale after push; empty commit resynced (land.sh guards now). Gap found: golden suite did not exercise #99 -> PR #104 adds read_range_pingpong (verified: reverting #99 fails only that trace).
- #75 (PR #102) source change was nemotron's (scoped brief); #74 done-nudge not yet done (H74 rerun with all fixes in progress).

- 2026-10-21 DONE: #104 and #105 merged (#74 closed). Milestone v0.2.4 issues #74 #75 #85 #88 all CLOSED; main at ce72047. #74 nudge: nemotron wrote helper+loop wiring (50 steps), finished by hand (line wrap, coverage, AGENTS.md, golden trace done_nudge).

- 2026-10-21 PO REDIRECT: benchmark/baseline (Layer 2) dropped as unmaintainable (archived in scratchpad/bench-archive, branch feat/bench local only). Replaced by e2e: PR #106 `e2e/` (real CLI + fault-injecting proxy `e2e/proxy.py` in front of ollama `tether-ollama` container localhost:11435; models gemma4:e4b qwen3:8b qwen3-coder:30b qwen3.5:9b). 38 scenarios, `TETHER_E2E=1 uv run pytest e2e`, local only. Hard asserts on tether behaviour (any model), real-model success = soft warning. Mutation-checked (4 fixes reverted -> matching scenario red). PO rule added to AGENTS.md: run e2e locally before every merge, result in PR, mitigate every failure.
  Gaps listed in docs/testing.md: sub-agents, pipelines, MCP, stats/retro/events/misses, other providers, web search, skill tools.py, --no-network, context budget #81.

- 2026-10-21 PO 'go ahead': merged #106 (e2e infra), then extended coverage in #107 -> 54 e2e scenarios (agents, pipeline, providers, MCP, web, skills tools.py, telemetry, --no-network, context budget), mutation-checked, e2e result 54 passed/91s. e2e rule in AGENTS.md satisfied (result in PR body).

## Next steps
- [x] #75/#74/#88/#85 all merged
- [ ] v0.2.4 release PR (version bump + release notes heading `## v0.2.4 (2026-10-21)`), PO OK needed
- [x] e2e merged (#106, #107)
- [ ] v0.2.4 release PR (version bump, dated release notes); PO wanted a green regression run first: e2e 54/54 is that. Needs PO go-ahead
- [ ] Remaining e2e gaps listed in docs/testing.md; cleanup worktrees/branches (ask PO)
- [ ] Clean up merged branches + worktrees (v024-*, exp-*, gold-demo) - ask PO
- [x] (all merged 2026-10-21 except #104) PRs opened 2026-10-21: #96 (#85 reap dead worker), #97 heredoc->stdin, #98 429 retry, #99 reads per range+window 8, #100 edit parse warning + SEARCH/REPLACE. Old local branch fix/88-provider-deadline (8 commits) superseded, unpushed.
- [ ] Merge order matters for docs/release-notes.md (each adds under '## v0.2.4 (unreleased)'; later PRs need trivial rebase)
- [ ] Watch CI on #96-#100
- [ ] Release notes v0.2.4 + release PR

## Sessions
| Date | Session note |
| 2026-10-20 | Created in worktree caveman-full-3e3119 |

## Wrap-up
- Outcome: v0.2.4 RELEASED. Release PR #108 merged (05bcf15), GitHub Release v0.2.4 'Regression Safety Net', delivery.yml success, PyPI tether-sdk 0.2.4 live, milestone v0.2.4 closed (#74 #75 #85 #88 all closed).
- Shipped PRs: #96 (#85), #97 heredoc->stdin, #98 429 retry, #99 reads per range + window 8, #100 edit parse warning + SEARCH/REPLACE, #101 (#88), #102 (#75), #103 golden traces, #104 ping-pong golden, #105 (#74 done nudge), #106 + #107 e2e (54 scenarios), #108 release.
- Final decisions: bench/baseline approach dropped as unmaintainable; regression strategy = golden traces in CI (deterministic, snapshot diffs) + local e2e behind a fault-injecting ollama proxy (assert tether behaviour, never model skill). AGENTS.md rule: run e2e locally before every merge, result in PR, mitigate every failure.
- Findings on using tether with nemotron-3-ultra: token knobs (fold, caps, ctx, steps, skill text) do not help on unscoped tasks in a big repo (340-780k tokens, no finish); scoped briefs (file + exact plan + test spec + edge cases) finish (#88: 32 steps/126k tokens; #85: 40/214k). On a tiny repo an unscoped task passes in 6 steps/4k tokens (repo size + exploration is the cost). Models write edits via bash heredocs/patch scripts; the `edit` tool needed tolerance (heredoc, unterminated SEARCH). Verify gates must use `.venv/bin/*` (no uv on sandbox PATH). NVIDIA free tier 429s need Retry-After + longer backoff.
- Follow-ups / debt: e2e gaps in docs/testing.md (pipeline verify gates/model routing, `mem pin --project`, `retro --apply`, Anthropic caching); the 'coding preset' idea became 'scoped brief template' (not shipped as a skill/file); main checkout /home/walkdead/Projects/tether is behind origin/main (not touched); PR bodies for #96..#108 mention nemotron-written pieces.
- Lessons: PR head can go stale after a push (empty commit resyncs; check headRefOid before trusting CI); golden suites need a trace per fix or the fix is unlocked (#99 gap); mutation-check every new test; `pkill -f` pattern can kill your own shell.
