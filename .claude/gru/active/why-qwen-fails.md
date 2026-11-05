# Why qwen3.5:9b fails Polyglot
- Slug: why-qwen-fails
- Status: active
- Started: 2026-11-04   Updated: 2026-11-04   Closed: —
- Branches / PRs: fix/model-sampling-defaults
- Budget: Haiku minions $2.42

## Goal
One reason that covers most qwen3.5:9b Polyglot fails (v0.2.13/v0.2.14) and one general change.

## Findings
- 50 failing traces classified by 8 Haiku minions (codebook in make_cards.py, local only). Primary: spec_misread 35, long_thinking_wall 6, loop_no_progress 5, other 2, whack_a_mole 1, test_output_unseen 1. Any: spec_misread 42, loop_no_progress 29, long_thinking_wall 18.
- Wrong design at about step 4, never revised. Repairs: 354 whole-file rewrites, 0 targeted edits. Failing count after a rewrite: better 39%, same 49%, worse 12%.
- Passes: 33/72 green at the first test run, 60/72 within 3. Fresh short attempts (best-of-k) estimated flat (0.52 against 0.53): exercises are bimodal.
- Empty turns: 94 turns where prompt+completion hit 8192 with no command (3.9% of turns, 40% of failing-run model time). Thinking runaway.
- About 15 earlier loop-envelope changes (stall, nudge, fold) were flat on full runs (R2 ledger).

## Sampling A/B (8 exercises, v0.2.14, 1 trial each)
| Arm | Runs | Pass | Overflow turns | Model time lost |
|---|---|---|---|---|
| temperature 0.2 (v0.2.10+v0.2.13 baseline) | 32 | 7 | 12.3% | 53% |
| 0.6 / top_p 0.95 / top_k 20 | 8 | 1 | 6.2% | 29% |
| 0.8 (Ollama default) | 8 | 3 | 5.4% | 28% |
Overflow halves. Pass flat within noise (4/16 against 7/32). Out dirs: north-star-c852b8/hosted-out/samp-{vendor,default}.

## Decisions
- 2026-11-04: drop the hardcoded temperature 0.2 in the ollama and openai adapters (PO: "commit what you've done"). Fixes the thinking runaway; does not fix the main cause (first design wrong).

## Round 2 (2026-11-04)
- e2e on fix/model-sampling-defaults: 80 passed.
- Room theory rejected: overflow is 10% even at 2-3k prompts (5k+ free); healthy command turns use p97 about 1.6-2.2k tokens. Thinking either ends short or runs away.
- Failure output hides the inputs: 1536 of 2304 traceback assert lines show only a variable (`total(basket)`), not the values. After a failing test run, failing runs re-read the test file next 27% of the time (passing 14%) and produce no command 17% (passing 6%); passing runs write the fix next 78% (failing 47%).
- R3 (Haiku, $0.14): feedback quality is the repair bottleneck (Olausson ICLR 2024), runtime values help (LDB ACL 2024), debugging decays after 2-3 tries (arXiv 2506.18403).
- Candidate: when a test fails, append the source of the failing test function (from the traceback frame in the workspace) to that observation. Bounded, 0 static tokens, no model call.

## Next steps
- [ ] Full 34x2 run with the change for the north star line
- [ ] New idea aimed at the first design (research card R3)

### 2026-11-04 thinking budget (T1)
- PO said "Yes, prepare it". Branch `feat/think-budget` (stacked on `feat/failing-test-source`).
- Verified on tether-ollama: `num_predict` counts thinking tokens; a cut reply has `done_reason: "length"` and empty content.
- Acceptance tests in `tests/providers/test_ollama.py` (5 new, 3 red before the change) + `tests/test_params.py` exact-options assert loosened.
- Card: `.claude/gru/why-qwen-fails/cards/T1.md` (owns `tether/providers/ollama.py`). THINK_BUDGET 2560; one think-off re-ask when cut with no command; caller `num_predict` (e.g. -1) disables it.
- src-ab arm B at 12/16 when written; book-store t0 passed in 150 s.
- T1 done by claude:haiku (1 attempt, $0.021, 18 turns; could not run uv in sandbox, verified by gru): 481 passed, cov 100%, ruff, mypy green; tests byte-identical. Commit `6cb036d` on `feat/think-budget` with docs (release notes, providers.md, AGENTS.md §D). e2e + A/B pending (GPU busy with src-ab).

### 2026-11-04 src-ab result (arm B = sampling fix + failing test source, 16 runs)
| metric | arm A (samp-default+samp-vendor, 16) | arm B src-ab (16) |
|---|---|---|
| pass | 4/16 | 4/16 (book-store, go-counting, scale-generator, vlq t0) |
| overflow turns | 5.4% / 6.2% | 9.2% |
| lost model time | 28-29% | 33% |
| rewrite better/same/worse | 56/26/19% (n=43) | 37/45/18% (n=38) |
| after failing test, fail runs: write / read_test / none | 48 / 25 / 14% (n=64) | 43 / 17 / 23% (n=53) |
- Read: source shown -> fewer test re-reads (25->17%), but more empty turns right after a failure (14->23%). Pass flat; n=16 cannot see < ~30 pt. Not a win yet, not a clear loss. The empty-after-failure turns are what T1 targets.
- Started arm C `hosted-out/think-ab` (feat/think-budget, 6cb036d: sampling + source + budget), e2e first. Log /tmp/claude-1000/think_ab.log.

### 2026-11-05 think-ab result (arm C = sampling + source + thinking budget, 16 runs), e2e 80/80
| metric | arm A (16) | arm B src-ab (16) | arm C think-ab (16) |
|---|---|---|---|
| pass | 4/16 | 4/16 | 6/16 (hangman t0+t1, book-store t0, vlq t0+t1, go-counting t0) |
| turns in 16 runs | 341 | 282 | 360 |
| empty window-filling turns | 20 | 26 | 1 |
| lost model time | 28-29% | 33% | 16% |
| after failing test (fail runs): none | 14% | 23% | 6% |
| rewrite better | 56% | 37% | 38% (n=61) |
- Budget does what it should: empty turns 26 -> 1, lost time halved, empty-after-failure 23 -> 6%. Pass +2 is inside noise at n=16.
- New limit: 7 of 10 failed runs end at the 30-step cap or 600 s, mostly near-passing (0.65-0.82). Rewrites still only 38% better: spec-misread remains the main cause.
