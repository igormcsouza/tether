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

## Progress log: Coding Ladder (2026-10-28 .. 10-29, backfilled from the session)
- 2026-10-28: v0.2.10 cut (#182,#184,#185,#186,#187). Full 34x2 Polyglot on qwen3.5:9b: 35/68 = 51.5% (baseline 35/68), mean 0.718 -> 0.763, wall caps 11 -> 14. Flat. Blanket think=false rejected (2/12); 16384 ctx rejected (-0.21, wall caps 11% -> 67%). Method fixed in #189 (bench/compare.py paired CI, --seeded, --tasks paired).
- 2026-10-28: Coding Ladder built (#190, #191, #193, #194, #201): bench/ladder (24 tasks, graders proven by validate.py, run.py --harness tether|naive|opencode|claude --single --provider ollama|nvidia|opencode, report/snapshot/charts). Max in-VRAM ctx: 9b 40960, 4b 81920, 7b 131072.
- Local results: 9b and 4b both write 3 / bugfix 3 / plan 6 / review 2; coder-7b write 2 / bugfix 0 / plan 1 / review 0. Harness table (24 tasks once): 9b tether 16 (0.82) vs bare 15 vs opencode 13 (6x slower); 4b tether 13 vs bare 16; 7b tether 1 vs bare 0. Tier 4 (unsaid cases) is a wall for every local model (#200).
- Fixes from the ladder: #192 (#177 green-test implicit gate), #195 (plain-text JSON tool call), #196 (edit --file/--content flags), #197 (wrap-up turn before read-only stall ends), #198 (done --stdin, edit --method). Issues #199 (63% of steps are reads, 24% repeats), #200 (tier 4).
- 2026-10-29: docs merged (#202): docs/ladder/{index,results}.md, bench/ladder/baseline, charts. Memory note: never `git add -A` in this worktree (bench output dirs untracked; 6156 files had to be untracked).

### Round 2: free hosted models (IN PROGRESS, not finished)
- Runner: /tmp/claude-1000/chain6.sh (nohup; finished marker /tmp/claude-1000/chain6.done). Data: hosted-out/<harness>-<model>/results.jsonl in the north-star worktree (untracked), logs /tmp/claude-1000/hosted-*.log. Models: nvidia/nemotron-3-ultra-550b-a55b, minimaxai/minimax-m3.1-flash (NVIDIA free API, key in NVIDIA_API_KEY), deepseek-v4.1-flash-free (opencode provider only; NVIDIA's deepseek-v4.1-flash never answers, OpenCode free tier is for its own client only so no tether/bare cell).
- Done (24 tasks once, ctx 32768): nemotron tether 19/24 (mean 0.918, 11.5 steps, 29 min) vs bare 16/24 (0.849, 4.7 steps, 20 min): tether helps a strong free model. minimax tether 6/24 (0.32, 195 min, some wall-cap timeouts) vs bare 6/24 (0.32): weak and slow, no harness difference.
- INVALID cells to redo: opencode on nemotron and minimax (0/24): HTTP 401 "authorization header missing", the `{env:NVIDIA_API_KEY}` apiKey in the workspace opencode.json is not resolved. Try provider `env: ["NVIDIA_API_KEY"]` in the config (do not write the key into the workspace file: the model can read it).
- Still running: deepseek via opencode (12/24 done; 1 pass so far; bugfix-5 took 11,075 s with steps=0: the wall cap (1200 s) did not kill that run, check run.py's poll/kill loop with sandbox.sh/bwrap children), then the two tether ladders (hosted-out/ladder-*).
### Next steps (resume)
- [ ] Wait for/inspect chain6 (hosted ladders), kill stuck opencode runs if still hung; fix the opencode 401 and re-run opencode nemotron/minimax.
- [ ] Re-run tether on qwen3.5:4b to check the -3 gap vs the bare loop (n=1 so far), paired seeds.
- [ ] Add round 2 to bench/ladder/baseline (snapshot.py), charts (charts.py MODELS is hard-coded to the 3 local models: make it data-driven), and a "hosted models" section in docs/ladder/results.md; PR + merge.
- [ ] Issues #199 (repeat reads), #200 (tier 4), #183 (empty thinking turns) remain open; v0.2.11 candidates.
