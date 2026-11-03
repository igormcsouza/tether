# North Star: Polyglot-Python 80% on qwen3.5:9b
- Slug: north-star
- Status: active
- Started: 2026-10-27   Updated: 2026-10-27   Closed: —
- Branches / PRs: branch fix/north-star-cheap-wins (worktree .claude/worktrees/north-star-c852b8), tracker #173
- Budget: warn 300k / stop 400k paid tokens, max escalations 3, Tier 3 never without ask   Used: ~small (gru only)

## Goal
Polyglot-Python (34 ex, 2 trials, `--poly-verify`, default 8192 ctx) pass rate on ollama/qwen3.5:9b: 51.5% -> 80% by v0.3.0. Lanes: default (official) and `swe` role (#172, must not score below default).

## Requests
- 2026-10-27 PO: "Get to the North Star"; dev too slow, benches unreported. Asked to review the last cross-session and close it (done: v0-2-bugs archived).

## Decisions
- 2026-10-27 PO answers: lane 1 = deterministic fixes first (no GPU); merge proof = tests + offline replay, one batched full 34x2 bench after 2-3 PRs, reported immediately; budget default 300k/400k.
- Ranked levers (Opus assessment): (1) runaway thinking hits num_ctx, +8-12pp, two attempts inconclusive (think=false 20 rows +3; length-retry rejected); (2) compact test output (relativize 195-char workspace path = 14% of obs chars, tracebacks = 51%), +3-6pp; (3) 4/68 runs died on 120s ProviderError timeout ~6pp (floor #171); (4) test-file access #170.
- STOP list: nudge variants, whole-set 24-run A/Bs, wall cap as part of the north star.

## Problems
- 14 exercises never pass: book-store bowling connect forth hangman paasio poker pov react rest-api scale-generator sgf-parsing transpose zipper. Bench GPU: 8GB RTX 5050, one Ollama.

## Plan (task cards)
- A: ollama default timeout 120 -> 300 (tests/providers/test_ollama.py test written; docs/reference/providers.md line 95 says 120). Gru patches (1 line).
- B: bash output: strip workspace prefix + ==== / ---- rule lines in sandbox.execute_bash_with_code (tests/test_sandbox.py test written). Gru patches (small).
- C (next): collapse unittest tracebacks; build bench/replay.py offline measure first.
- Then: output headroom / bounded thinking (#135/#147), #170, #171.

## Ledger
| Task | Tier | Model | Harness | Session | Attempt | Tokens | Time | Result |
|---|---|---|---|---|---|---|---|---|
| A,B | plan | gru | - | - | 1 | small | - | tests written failing, patch pending |

## Progress log
- 2026-10-27 branch fix/north-star-cheap-wins; failing tests added (sandbox prefix, ollama timeout). Closed v0-2-bugs log.

## Next steps
- [ ] Patch A and B, update docs (providers.md, release notes), unit+e2e, PR with `north star:` line
- [ ] bench/replay.py offline proof for B
- [ ] One batched full 34x2 after A+B+C, report at once

2026-11-03 (never-pass experiments, all negative, nothing shipped)
- 11 exercises that never pass in v0.2.13 (bowling connect forth hangman poker pov react scale-generator sgf-parsing transpose wordy). Two failure classes: re-reading the 6-11k char test file in chunks (bowling 19 of 30 steps, forth, poker, react) and 3-6k token first-write thinking turns hitting the 600s wall cap (connect, pov, hangman, scale-generator, transpose).
- Lever A, fold unittest failures with the same error into one block (-13% obs chars): 1 pass in 10 runs (hangman t1, baseline 0 of 2), bowling 0.45/0.39 unchanged. Run dir hosted-out/INCOMPLETE-fold-failures-10of22 (db nested in ws/ because --out was relative; use absolute --out).
- Lever B, 16k context on bowling: 0.16/0.29, still 19 test greps. Context size is not the blocker. hosted-out/ctx16k-readheavy.
- Lever C, nudge on 2nd full rewrite pointing to `edit replace`: forth 0.167/0.167 (baseline 0.8-0.93), nudge fired, model never used edit replace. hosted-out/rewrite-nudge-forth.
- Across 68 v0.2.13 runs: fail runs rewrite file 4.8x, pass runs 2.5x, zero `edit replace` in any run. The 9B model does not patch.
- Code parked as local commit 0c8c51f on branch feat/dedupe-test-failures (not pushed, not for merge).
- Rule learned: stop after 2 fails in a row and rethink (memory stop-on-two-fails).

2026-11-03 (loop root cause, analysis only; release v0.2.14 prepared on release/v0.2.14 worktree, NOT pushed, PO said hold)
- 68 v0.2.13 runs: failed runs 24.5 steps, 7.4 test-file reads, 5.4 exact command repeats; passed 12.3 / 1.6 / 3.1. Loops track failure but follow being stuck.
- Hypothesis "model cannot see its own written file" FALSIFIED: all 241 file writes are bash heredocs (`cat > f <<EOF`), whose full text is in the replayed tool call. No `edit write` use at all.
- bowling t0 (16k): every test fails with `ValueError: cannot roll` at bowling.py:14 (its own code, shown in the output); model never opens bowling.py, greps the test file 20 times (4 identical repeats, 5 empty greps). Misdiagnosis, not missing information.
- Untested leftover levers: treat `cat f | grep ...` pipelines as reads in live_read_obs (answers an exact repeat with a pointer, saves tokens, no steering); fair plain baseline.

2026-11-03 pipe-read dedupe (cat f | grep ... counts as a read; repeat gets the #199 pointer): bowling x2 on qwen3.5 8192: 0.129 / 0.065, FAILED at 30 steps, test-file reads 14 / 17 (baseline ~16), pointer fired 1 / 4 times and the model went on regardless. No change in behaviour: stopped per rule. Parked as local commit on branch feat/pipe-read-dedupe (worktree .claude/worktrees/pipe-reads), not for merge. Run dir hosted-out/pipe-dedupe-bowling.
