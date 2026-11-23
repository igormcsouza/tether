# v0.3 backlog (bugs, sandbox, fold window)
- Slug: v0-3-backlog
- Status: planning
- Started: 2026-11-08 21:11   Updated: 2026-11-08 21:11   Closed: —
- Branches / PRs: —
- Budget: to be set in the preview   Used: —

## Goal
Implement the remaining v0.3 items with tether minions only (qwen weak, haiku mid, opus strong, all through tether; Claude Code only as per-card fallback): bugs #267 #268 #269 #271 #273 #278 #279 #280, sandbox #124 (+#59; #9 stays open), fold window #205.

## Decisions
- 2026-11-08 21:11 First run of Gru v2 here: wrote local.yml, gru.yml, store .gitignore, ~/.config/gru/profile.yml (team versioning, store `.claude/gru/`, bwrap, qwen limit 1, haiku/opus limit 3, fallback claude, file_tether_issues allow).
- Scope = everything in one preview; keep #9 open (not combined with #124); merge green PRs after local e2e, release only on the PO's explicit yes.
- #59's remaining gap is #124 item 4 (escalation).

## Gru feedback
- Store: main repo root has no `.claude/gru/` (checkout stale); used the worktree's committed store.

## Progress log
- 2026-11-08 21:11 request received, interview done, issues 124/205/59/267-273 read; preview next.

- 2026-11-08 21:40 PO accepted: wave A + B0 + C1, stop 1.8M / warn 1.4M paid tokens; haiku parallel unlimited ("hard cap only depends_on"). Base branch gru/base in the describe-failures worktree; scripts in scratchpad g2/ (mkws, stage, pipe1, pipe2, pin). Cards A1 A3 A4 B0 written; pipe1 started for A1 A3 A4 (plan haiku, tests qwen under flock, check haiku) and B0 (haiku audit).

- 2026-11-08 21:50 B0 first run asked 2 questions (card lacked the issue text; PLAN.md vs read-only conflict). Fixed the card, reran: audit in scratchpad g2/B0-audit.md (items 2,6,9 not done; 1,3 partial; 4 split; 5 drop; 7 done; 8 verified not done by grep). Plans for A1 A3 A4 A5 A6 done (haiku, ~30-40k tokens each); A3 tests running on qwen.
- 2026-11-08 21:50 Gru feedback: a card must paste the issue text; a minion cannot read GitHub. Read-only cards need an explicit "no file" output rule that the generic brief does not override.

- 2026-11-08 22:05 Tether friction/finding: qwen tests stage on A3 = 40 steps, 705k tokens, WAITING_INPUT, stub tests (pass bodies); same pattern as the last run. PO approved: haiku writes the tests, qwen only builds (tests= slot in g2/slots). Killed queued qwen test runs; pipe1b (tests haiku, pin, check) started for A1 A3 A4 A5 A6.
- 2026-11-08 22:05 PO has not yet answered the sandbox cut (drop item 5, defer done --ask, fail-closed opt-in); wave A continues meanwhile.

- 2026-11-08 22:30 Finding: the killed qwen `tests` stage had edited product files (A3 declarative.py, A4 cli.py/api.py/cli.md) instead of only writing tests. Rebuilt ws A3 and A4 from base keeping the haiku tests and PLAN.md (g2/reset.sh), re-pinned. Gate step must always diff the workspace against base (g2/contam.sh) before build. Tests A1 A3 A5 A6 pinned; A4 pinned after fix round (check says only the cli.py help text left, a builder job). Builds: A6 running (qwen), A1 A3 A5 A4 queued.

- 2026-11-08 22:45 A6 build (qwen, 45 steps, 529k tokens, WAITING_INPUT out of steps): core code right (pathspec excludes, 100% coverage, mypy ok). Gate fails: qwen rewrote docs/release-notes.md and DELETED the other Unreleased entries (same family as tether#267, `edit write` on an existing file), dropped trailing newlines, one ruff import-sort error. Restored release-notes.md from base in the ws and queued a focused qwen fix card (g2/briefs/A6-fix1.md, replace-only, gates: pytest 3 files + ruff). Tether friction candidate: qwen uses whole-file write on docs despite the card saying edit replace.

- 2026-11-08 23:10 Wave A status: A1 merged (#282, qwen first try, 22 steps). A6 passed gate after one focused qwen fix (code ok, but qwen wiped other release-note entries first). A3: qwen build 1 broke the retry loop (no break) and edited the pinned test; after an opus delta plan, build 2 wrote SEARCH marker text into declarative.py (IndentationError). A4: qwen 45/45 steps, 14 ruff errors, suite hangs in the gate. A5: qwen build 1 wrote a syntax error into edit.py; opus delta plan done, rebuild running. Pattern: qwen on S cards touching big existing files burns all 45 steps and corrupts files; only A1 (one-line change) passed first time. Tether friction candidates: `edit` SEARCH/REPLACE markers end up in files; qwen whole-file rewrites; step budget exhaustion. Stop-on-two-fails: pause qwen builds, ask PO to bump A3/A4/A5 swe to haiku.

- 2026-11-08 23:55 A6 merged (#284, e2e 125 passed, CI green). A5: gate green after opus plan + qwen (14 steps) but haiku review found 2 blockers (empty REPLACE body still wipes the file; empty SEARCH raises IndexError); opus delta plan 2 running, then haiku adds tests (tests2 stage), qwen fixes. Harness fixes of mine: minion output files per pid, qa/review brief says plan already applied.

- 2026-11-09 00:20 PO approved the bump: haiku builds A3, A4, A5 (qwen failed A3 x2, A4 x1, A5 x3, even with opus delta plans; only the one-line A1 and the focused A6 fix passed). Workspaces A3 A4 A5 reset to the new base (888fb9d) keeping tests + PLAN; builds running with haiku in parallel (pipe2h). Calibration: S/weak first_pass so far 1 of 5.

- 2026-11-09 00:40 Haiku builds all gate-green on the first try: A4 12 steps (730 tests, 100%), A3 10 steps (728 tests; only formatter-style change to the pinned test file + the expected update of the old test_command_timeout), A5 7 steps (731 tests, 100%, both review blockers' tests pass). ~180k tokens each. Paid tokens logged ~1.67M before these (warn 1.4M crossed); qa/review for A3 A4 A5 held until the PO answers the cap question.

- 2026-11-09 00:50 PO raised the paid-token cap for this feature: warn 2.4M, stop 3.0M. qa + review started for A3 A4 A5 (haiku, parallel).

- 2026-11-09 02:10 Merged: A1 #282, A6 #284, A5 #285, A4 #286, A3 #287 (all haiku-built except A1/A6 qwen). PO decisions: cap raised to 11M (warn 9M) for everything; sandbox plan accepted (S1 refusals, S2 fail-closed without bwrap as a 0.3 breaking change, S3 opt-in rlimits, S4a allowlist file + S4b escalate-by-send, S5a docs network pattern, S5b web domain allowlist, S6 violation event + stats, S7 conformance suite). Cards written for A2 A7 A8 S1-S7 C1. Slots: haiku default, opus for planner/qa/review on M/high risk, opus swe for S4b and C1 (L). auto1 (mkws, plan, tests, pin, check) launched for A2 A7 S1 S5a S5b C1 in parallel; A8 waits on A2, S2..S7 chain after S1. Side question from PO: bigger local model (qwen3-coder:30b already installed 18.6GB; 35B-A3B ~22GB; Coder-Next ~48GB does not fit 8GB VRAM + 31GB RAM); proposed a paired mini-lab after the queue, not started.

## Next steps
- [ ] PO accepts preview; write card files; run wave A (bugs).

- 2026-11-09 03:05 PO: finish all cards with minions, report the coder lab, then merge everything, CUT v0.3.0 (explicit yes given in chat) and install it locally; nothing more. Side question qwen3.6:35b (23GB, ollama): wait for qwen3-coder:30b lab first; no download without OK. Status: gates green A2 (after haiku fix to an old test), A7, S1, S5a; qa/review running for A2 A7 S1; S5a qa has 1 should-fix (state whether --verify runs in bwrap; strengthen test); S5b and C1 builds running. Mistake: launched pipe3.sh (tests2 + qwen rebuild) on A2/A7/S1 by name confusion, stopped within seconds, workspaces verified intact. Flake: tests/test_command_provider_retry.py::test_gives_up_with_provider_error failed once under CPU load, passes alone (tether friction candidate).

- 2026-11-09 ~02:45 LAB RESULT (paired, same brief/tests/plans, 45 steps, 32k ctx): 0 of 6 runs passed the gate. A3: 9B 571s, 678k tok, edited pinned test + ruff errors; 30B 1337s, 493k tok, pins intact, ruff ok, but suite fails (retry test). A4: 9B 346s, pinned test edited, ruff+import error; 30B 921s, 24 ruff errors, collection error. A5: 9B 260s, 2 ruff errors, target test fails; 30B 454s, deleted tether/tools/edit.py (ModuleNotFoundError). All 12 hit 45/45 steps. 30B is 1.7-2.3x slower, left pinned tests alone (9B edited them twice) but broke more of the product. Verdict: no gain over 9B on these cards; do not pull qwen3.6:35b (23GB, more RAM offload, slower). Haiku built all three first try (7-12 steps). e2e batch for A2 S1 A7 S5a S5b C1 started (g2/e2eall.sh).

- 2026-11-09 ~03:20 PO raised the paid-token cap: warn 25M, stop 30M (usage was ~15.7M: haiku 11.4M + opus 4.3M by spend.py, counts all prompt tokens). Merged: A2 #288, S1 #289, A7 #290, S5a #291, S5b #293. Open: A8 #294 (e2e 138), C1 #292 (PO sign-off pending). S2: haiku build failed gate twice (6 pinned tests red), bumping swe to opus after a second delta plan. Coder lab: 0 of 6 passed, no gain vs 9B (see earlier entry).

- 2026-11-09 09:55 PO: "merge C1" given and done (#292 merged after merge-with-main, full suite 906, e2e 142, CI green; retest 1 on main: 906 + 142). PO also asked to test and retest C1 on main: paired bench (benchc1.sh, before df93701 vs after c5fab08, qwen3.5:9b, paired set, seeded, 1 trial = 10 pairs) running. Merged so far: A2 A7 A8 S1 S2 S5a S5b C1. On branches, not merged (e2e waits for the bench, shared GPU): S6 feat/sandbox-violation-stats (922 tests), S4a feat/sandbox-allowlist (988 tests; review blocker on git config fixed and verified by probe, reviewer overruled; QA's other items fixed). S3 gate green (912) but opus qa/review not done. ACCOUNT LIMIT: the softmedium account hit its 5-hour limit at ~09:50 (haiku and opus both return "resets 1:30pm America/Fortaleza"), so S3 qa/review, S4b and S7 and the final release wait for ~13:30. Gru overrode two wrong review blockers with evidence (S6: tests in the _cov file; S4a: matcher probe). Friction for tether: pinned-test timing (S3 limits test 35 s), opus empty-response error is shown as a worker error with no hint of the usage limit (tether should surface the provider's `result` text).

## 2026-11-09 checkpoint
- C1 bench: no regression (pass .50->.60, steps 16.3->12.1, CI spans 0), posted on #205.
- Merged S6 (#296), S4a (#297); e2e 143 / 146 passed. Remaining: S3 (qa/review), S4b, S7 blocked by paid 5h limit until ~13:30. Release v0.3.0 after.

## 2026-11-09 14:30 checkpoint
- S3 merged #298 (opus qa+fix+review). S7 tests exposed real bug: bwrap /dev/null mask is nodev, so git status/grep -r fail in jail; card S8 (empty-file mask) added ahead of S7.
- Paid 5h limit hit again 14:26, resets 18:30. S8 plan+tests pinned; S4b plan+tests+check done, tests2 and build failed on the limit; S7 tests built, waits for S8.
- Friction: tether shows a provider limit only as a bare worker_error with zero tokens.
