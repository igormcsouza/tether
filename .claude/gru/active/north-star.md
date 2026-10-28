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
- 2026-10-27 merged #180 (timeout 300s, compact bash, canary). PR #181 traceback collapse (canary +0.12, offline -12.6% obs chars, e2e 69). PR #182 outage retry (#171, e2e new scenario). PO: 80% is the impossible focus goal; wants v0.2.10 plan ranked by north star. Canary tool: bench/canary.py (12 min, 7 rows). Note: bench `pass` is graded by exercise tests, so #177 (done at max steps) does NOT move the bench number, only the user-facing floor.
