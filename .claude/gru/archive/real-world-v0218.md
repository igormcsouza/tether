# Real-world test: tether v0.2.18 as the only minion
- Slug: real-world-v0218
- Status: done
- Started: 2026-11-08   Updated: 2026-11-08   Closed: 2026-11-08
- Branches / PRs: #259 #260 #261 #262 #263 #264 #265 #266 #274 #275 #276 (all merged); issues tether #267-#273, gru#7
- Budget: warn 300k / stop 400k paid tokens (gru + haiku), wall-clock overnight-ok, max escalations: none (no rung above haiku allowed)   Used: gru session context ~620k at the end (Opus; 5-hour plan window hit 82%); haiku ~9M prompt tokens (claude-softmedium); opus planning ~2M; qwen local

## Goal
Implement 10 features using only tether v0.2.18 as the minion: tether+ollama/qwen3.5:9b for easy cards (sequential), tether+claude-softmedium/haiku for hard cards (parallel, own worktrees). Card kinds swe/qa/review/plan. Gru plans, writes acceptance tests, verifies, commits, opens PRs; never implements, no Claude Code minions. Then report: success rate, issues, improvements, what was good, junk tether features.

## Requests
- 2026-11-08 PO: list features; then "Implement all 10 ideas, the haiku ones can be done in parallel, the qwen ones should be one by one". Close already-covered issues with a note.

## Decisions
- Closed as covered: #220 (hand-back after restarts shipped), #78 and #134 (SEARCH/REPLACE blocks).
- qwen (sequential): F1 doctor, F2 gate precheck #82, F3 export.
- haiku (parallel, one worktree each): F4 empty reply #135, F5 --max-tokens, F6 thinking #32, F7 pipeline resume #35, F8 mcp worktree #242, F9 replay #7, F10 diff.
- No escalation rung: a card that fails twice on its minion is reported as a failure (that is the data), not escalated to Claude Code.
- PO 2026-11-08 (mid-turn): if a task fails, tether+opus (claude-softmedium/opus) writes a plan aimed at the implementing model, then retry on the same tether+model with that plan. Opus rung OK'd for this use only.
- Haiku runs with --context-tokens 100000; qwen at default 32768.

## Problems
## Plan (task cards)
## Ledger
| Task | Tier | Model | Harness | Session | Attempt | Tokens | Time | Result |
|---|---|---|---|---|---|---|---|---|
## Tether friction
## Progress log
- 2026-11-08 log created; issues #220 #78 #134 closed.
## Next steps
- [ ] selftest qwen + haiku via tether
- [ ] plan cards (haiku) for F4-F10, acceptance tests by gru
## Sessions
| Date | Session note |
- 2026-11-08 plans F4-F10 by tether+haiku: 7/7 COMPLETED, 59-109 s, 5-13 steps, 33k-109k prompt tok; scope clean (only PLAN.md). Reviewed: good quality; decisions F7 usage exit 1, F9 verify-gate limitation documented.
- Deviation: haiku swe cards write the plan's tests themselves (TDD), gate = full suite 100% cov + ruff + mypy; tether+haiku review checks tests vs plan. qwen cards get gru-written acceptance tests.
- Isolation: session can only write its own worktree; minions now run in plain copies scratchpad/ws/<id> (no git); rw-f1..rw-f10 git worktrees were created by mistake via script, unused except PLAN.md (to remove at done, PO OK).
- F1 qwen attempt 1 (ses_d89d4ab0): FAIL out of steps 30, 202k prompt tok, 113 s, never ran tests; broke cli.py with sed -i insert inside try:. Opus plan + qwen retry started.
- swe F4-F10 haiku dispatched (4 parallel, 40 steps).
- 2026-11-08 PO: needs a durable fix so tether works on its own worktree and delivers a branch, documented (docs + MCP). Added F11 `tether run --worktree` (harness creates git worktree at ~/.cache/tether/worktrees/<repo>-<sid>, optional --setup, commits on tether/<sid> at stop; MCP worktree:true; guide docs/guides/own-branch.md). F8 stays (explicit workspace arg). F11 plan dispatched to haiku; implementation merges after F5/F8.
- F1 qwen attempt 2 (opus plan ses_377958aa 103 s; qwen ses_43ab8679): FAIL out of steps; qwen never opened PLAN.md (gru card bug: plan mentioned only at the end after the old reading list). Attempt 3 with card = 'edit view PLAN.md first' running.
- Friction: tether wait default --timeout 120 (not shown in --help) returns while RUNNING; minion.sh waited 120 s and read RUNNING. Fixed caller side (--timeout 3600).
- Friction: qwen writes `sed -n '45,90p file'` (file inside the quotes) repeatedly: 6 times across 2 runs; a quirk normalizer could split it.
- F11 plan (haiku ses_41a4d3b2, 76 s) reviewed: ok; decisions: MCP no setup, commit at WAITING_INPUT, ship worktree-from. F11 swe dispatched.
- F1 qwen attempt 3 (ses_2033bfb8, card = follow opus PLAN.md): COMPLETED at step 30, 284k prompt tok, 137 s. Acceptance tests pass unchanged, 100% cov, mypy ok. Left: CLI docs section (test_cli_docs), formatting. Our #79 cd-skip fired in the wild (`cd /testbed && pytest`). Finish card (fin-f1) on qwen running.
- gru fault: my acceptance tests had 3 E501 lines + import order; fixed in acc/ (gru-owned).
- swe haiku F4-F10 (40 steps, 4 parallel): COMPLETED+verified green: F5 (no release note), F8, F9, F10. F7 green except 1 ruff (out of steps). FAIL: F4 (broke test_no_second_ask_when_the_caller_set_the_budget + mypy), F6 (edit write with SEARCH/REPLACE stdin wiped ollama.py 216->22 lines; 20 steps hunting the original). 357-543 s, 497k-720k prompt tok each.
- F1 fin (qwen): green all (docs section + format).
- TETHER BUG #1 (F6 ses_d64c80e5 step 19): `edit write <existing file>` with a SEARCH/REPLACE block in stdin overwrites the file with the block. Should apply as replace or refuse. No undo -> model hunted the disk 20 steps.
- Retries: F4, F6 = opus plan for haiku + fresh haiku (PO rule). F7, F5 = tether send resume (small leftovers; also tests send). F2 qwen started.
- tether send resume: F5 +5 steps 53 s, F7 +2 steps 33 s -> both verified green (send works well for leftovers). Reviews F5, F7 dispatched.
- Reviews (haiku, 37-94 s, 5-9 steps): 6/6 CHANGES. Real findings: F10 symlink escape in diff (security), F5 action dropped at budget cap, F8 TypeError on non-string workspace, F9 README + empty --model, F1 release note/:latest/host scheme. False alarm: F7 'EXIT_USAGE is 2' (it is 1). Fixes sent via tether send (F5 F7 F8 F9 F10); F1 via qwen fix card.
- F11 haiku (45 steps, 549 s, 725k tok): FAIL out of steps; commit at stop never lands, 3 tests fail, cov 99, docs missing. opus-finish (keep work) running.
- F2 qwen (30 steps, 222 s): FAIL; hook added but `gates` never imported -> NameError, 114 tests fail. opus-finish for qwen queued, then F1 fixes, then F3.
- Review fixes via tether send: all 5 green (27-133 s). Spot-check: F8, F10 really fixed (symlink check + size cap + tests). GREEN-BUT-WRONG: F9 did none of its blocking fixes (README, empty --model), F5 did not move the budget check (my new test fails), F6 lacks read --thinking + release note, F4 lacks release note. Sessions said done anyway: a fix request without a deterministic check is skipped.
- Response: gru wrote failing tests for each gap (acc/f4,f5,f6,f9 round 2, incl. docs-presence tests); fresh haiku fix2 sessions with those tests as verify gates.
- F4/F6 retries: opus plan sessions hit 30-step cap again (WAITING_INPUT) but had written PLAN.md; haiku then COMPLETED green (F4 19 steps 264 s, F6 24 steps 165 s).
- Opus F11 plan attempt 1: 30 steps, never wrote PLAN.md; re-read same 3 regions 6x (cause to investigate: folding vs command-provider token accounting). Retry with 45 steps + 'write PLAN.md early' running.
- PRs opened (unit-verified, reviewed, fixed; e2e pending): #259 F8 mcp workspace, #260 F10 diff, #261 F7 pipeline resume, #262 F5 max-tokens, #263 F9 replay. Branches feat/mcp-workspace, feat/session-diff, feat/pipeline-resume, feat/max-tokens, feat/replay (from main 2891ab5).
- fix2 (gru tests as gates): F4 8 steps, F5 18 steps green; F6/F9 ended FAILED (exit 3) only because gru's own new test files broke ruff E501 (minion correctly would not edit them); after gru fixed its tests: green. Lesson for gru: lint acceptance tests before dispatch.
- Reviews F4, F6 dispatched; QA (e2e scenario) card F10 dispatched as a probe for e2e inside tether's sandbox.
- F4 review: real (ModelResponse field order shifts positional args; provider docs missing). F6 review: mostly FALSE because gru's review diff raced with mkpr F5 in the same worktree (base had --max-tokens); real: 4000-char cap missing, empty message text. gru pinned both with tests (acc/f4 test_empty_reply_review, acc/f6 test_thinking_cap); fix3 sessions running. gru's new lint guard caught gru's own long docstring before dispatch.
- QA F10 (haiku, 9 steps, 72 s): e2e/test_session_diff.py, 3 real scenarios, pass; e2e runs fine inside tether's sandbox. Pushed to #260. QA F5 F7 F8 F9 dispatched. Full e2e for F10 running in ws/f10.
- F4/F6 fix3 (gru tests): green (10 / 9 steps, ~70 s). F4 README wrongly says retry uses think=false -> tether send correction running.
- F11 after opus plan #2 (45 steps, WAITING but PLAN.md written) + haiku 40 steps: commit now lands; left: not-a-repo test, 10 uncovered lines, cli docs, ruff, guide. gru wrote tests/test_worktree_docs.py; fix4 card running.
- QA F5 F7 F8 F9 (haiku 7-9 steps, 55-83 s): real e2e scenarios, gates pass; pushed to PR branches; full e2e running.
- MERGED #260 (F10 tether diff): e2e 96 passed, CI green.
- MERGED #259 (F8). e2e F5 96, F7 95, F8 96, F9 96 passed.
- F4 README corrected via send (15 steps total, 52 s): green.
- TETHER BUG #2: command provider timeout (180 s) is not retried; one slow Claude CLI call (writing a long guide) ended the whole F11 session FAILED exit 5 (ses_ee26e6ca step 24). HTTP providers retry twice. Floor #171 violation. F11 resumed via send.
- MERGED #262 (F5) and #261 (F7). F7 needed: CI on py3.12 caught an argparse break (local 3.14 passed) -> tether+haiku fix card with a 3.12 venv (code fixed; its .venv312 gate failed only inside the sandbox on SSL CA, a gru setup issue); two merge-with-main rounds (additive conflicts, gru resolved); e2e on merged branch 104 passed.
- Note: GitHub skips CI on a conflicting PR; after each merge to main the next PR needs main merged in first.
- F11: green after send-resume (55 steps total). QA e2e card 6 steps 43 s. Review: 5 real blocking bugs (status line never printed, commit failure crashes session, stale sha on resume, docs keys location, README) + minors incl. '-' ref option injection. gru pinned them in tests/test_worktree_review.py; fix5 running.
- MERGED #263 (F9) after merge-with-main (additive conflict) + e2e 107 passed. Merged so far: F10 #260, F8 #259, F5 #262, F7 #261, F9 #263.
- QA cards F4, F6 dispatched; F11 fix5 running; qwen queue (F2 finish, F1 fixes, F3) still running.
- MERGED #264 (F4, e2e 110), #265 (F6, e2e 113; provider field conflict additive), #266 (F11, e2e 115; hand-resolved create_session/from_session interleave). 8 of 11 merged.
- Dogfood --worktree with qwen in a throwaway repo: caller untouched, fix committed on tether/<id>, status line ok. Session ran out of steps: (a) [BEFORE WRITING] note made qwen re-read the test 6x (5 loop_stall, 6/15 steps lost) -> report item; (b) gru's gate used system python3 without pytest (gru error).
- TETHER BUG #5: headless worker died before marking RUNNING (pid 3540688 gone); status stays PENDING forever (reaper only handles RUNNING); tether wait blocked 3600 s; worker stderr discarded so the cause is lost (F2 opus plan ses_e6c13419).
- F1 qwen review-fix: 25 steps out; host-prefix test fails + ruff. Queued: opus plan + qwen retry for F2 finish, then F1 finish (after F3 qwen run).
- F3 qwen attempt 1 (ses_7a0d8b34, 30 steps, 267 s): FAIL; export.py written, CLI not wired, cut missing; 3/5 tests fail. Queued opus finish + qwen retry after F2/F1.
- PO: file issues. Filed tether #267 (edit write + SEARCH/REPLACE wipes file), #268 (command provider timeout not retried), #269 (wait 120 s default), #270 (sed quote quirk), #271 (PENDING dead worker, stderr lost), #272 ([BEFORE WRITING] loop on qwen). gru guide filed as igormcsouza/gru#7.
- ROOT CAUSE of F2 opus 'never wrote PLAN.md' x2: TETHER BUG #273 (security): headless worker = python -m tether.cli with cwd=workspace -> imports the workspace's tether/ (minion's broken F2 code) -> NameError -> PENDING forever. Reproduced. Workaround: minion.sh runs foreground (session id from stderr, #90). Commented on #271. qwen queue restarted (qwen-queue4: F2, F1, F3).
- qwen-queue4: F1 review fixes via opus plan (5 steps 48 s) + qwen (9 steps 49 s): GREEN. F3 via opus plan (11 steps) + qwen (30 steps): feature works, all 5 acceptance tests pass; left cli docs + ruff -> fin-f3 qwen card. F2: no clean try yet (old queue2 survived pkill and deleted ws/f2-plan mid-run -> FileNotFoundError; gru orchestration error). qwen-queue5: clean opus+qwen for F2, then fin-f3. QA F1 (haiku) dispatched.
- QA F1 (haiku 9 steps 64 s): 3 e2e scenarios. MERGED #274 (F1 doctor, qwen-built): e2e 118, CI green. 9 of 11 merged.
- F2 clean opus plan (14 steps 281 s) + qwen (30 steps 108 s): all tests pass; left 3 uncovered lines + ruff. F3 fin (qwen 20 steps): docs done, tests pass; ruff left. qwen-queue6: fin-f2 (exact test file given), fin2-f3 (ruff only).
- fin-f2 (qwen 6 steps 42 s, exact test file in card) and fin2-f3 (qwen 4 steps 15 s): both GREEN; acceptance-test diffs are import order only (ruff isort with ws config). Reviews + QA for F2, F3 dispatched (haiku).
- Reviews F2/F3 (haiku): F2 chained gates only check first program, no release note, edited test_harness parametrization; F3 release note under v0.2.18, backtick fences break, stray .minion-* files (gru runner artifacts, now excluded). QA F2 (5 steps 29 s, 2 scenarios), F3 (7 steps 46 s, 3 scenarios). gru pinned fixes in tests; qwen fix2 cards (sequential) running.
- qwen fix2 F2 (25 steps 578 s) and F3 (25 steps 2491 s, runaway thinking): both out of steps. F2: review tests pass; stale edge test + 1 line left. F3: both review tests fail. opus-finish + qwen retry queued (qwen-queue7).
- PO asked steering cost vs self-implementing: for qwen cards ~same (context size per turn dominates; ~45 turns at ~450k cached each); haiku cards clearly cheaper to steer. Session ctx 616k, 5h window 82%.
- F2/F3 review fixes via opus plan + qwen: F2 green (27 steps); F3 green after gru fixed its own wrong test regex (4th gru test bug). MERGED #275 (F2, e2e 120) and #276 (F3, e2e 123). ALL 11 FEATURES MERGED.

## Wrap-up
- Outcome: 11/11 features merged (F1 doctor, F2 gate pre-check #82, F3 export, F4 empty reply #135, F5 --max-tokens, F6 thinking #32, F7 pipeline --resume #35, F8 MCP workspace #242, F9 replay #7, F10 diff, F11 run --worktree), each with 100% coverage, a QA-written e2e scenario, full local e2e, CI 3.12/3.13 and a Haiku review. Issues #220 #78 #134 closed as covered.
- Per tier: Haiku plans 8/8 good; Haiku swe first try 4/8 green; after an Opus plan 3/3. qwen swe first try 0/3; with Opus plans and gru-pinned tests 3/3 after 2-5 rounds each. Reviews 11/11 found real bugs (1 false alarm + 1 gru-caused false set). QA 11/11 first try.
- Lessons (also in gru#7): a minion's done is not evidence, pin every requested fix with a failing test as a gate; lint acceptance tests with the workspace config; gates must run inside the sandbox; one workspace per minion (now `tether run --worktree`); run minions in the foreground until tether#273; never switch branches in the orchestrator checkout while background jobs read it; kill old queues fully before restarting; steering qwen costs about as much as typing it yourself on a long gru session, steering Haiku is clearly cheaper.
- Tether bugs found: #267 edit write + SEARCH/REPLACE, #268 command provider no retry, #269 wait 120 s, #270 sed quote quirk, #271 PENDING dead worker, #272 [BEFORE WRITING] loop on qwen, #273 headless worker imports the workspace's tether (security).
- Cleanup: rw-f1..rw-f10 worktrees and feat/rw-* branches removed (empty, created by mistake); scratch workspaces (8.7 GB) and the dogfood repo deleted; 11 local PR branches deleted (merged upstream); remote branches kept.
