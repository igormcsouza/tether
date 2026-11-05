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

## Next steps
- [ ] Full 34x2 run with the change for the north star line
- [ ] New idea aimed at the first design (research card R3)
