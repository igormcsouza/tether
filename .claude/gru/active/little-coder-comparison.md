# Compare tether with little-coder on Polyglot-Python (#218)
- Slug: little-coder-comparison
- Status: active
- Started: 2026-11-04   Updated: 2026-11-04   Closed: —
- Branches / PRs: branch feat/bench-little-coder (worktree .claude/worktrees/describe-failures), issue #218; parent north star #173
- Budget: warn 300k / stop 400k paid tokens, GPU runs free, max escalations 2 (Haiku -> Sonnet)   Used: ~small

## Goal
Know whether 80% on qwen3.5:9b is reachable with a harness built for small models, and what it does differently. Same 34 Polyglot-Python exercises, same verify gate, same model, 16k context as the issue says (tether also at 8192 for reference).

## Requests
- 2026-11-04 PO: "run this plan of yours please!" (accepted the 4-card plan below; start at Haiku on claude tiers).

## Decisions
- PO accepted: research -> adapt runner -> run -> report. Gru does not type product files; minions run through the claude harness (sandbox.sh) in this workspace.
- v0.2.14 release still on hold; #221 merged (restart + hand-back).

## Problems
- Earlier Haiku subagent (Agent tool) wrote to its own worktree; use the claude harness recipe, not isolated subagents.

## Plan (task cards)
| id | kind | output | harness / model | tier |
|---|---|---|---|---|
| lc-1 | research | `bench/little_coder_recipe.md`: how to install and run little-coder against Ollama qwen3.5:9b headless on one task dir, and how to read its result | claude / haiku | 1 |
| lc-2 | swe | `bench/run.py` runner `littlecoder` (same task dirs, same verify gate), tests | claude / haiku -> sonnet | 1-2 |
| lc-3 | run | results.jsonl for 11 never-pass x2, then all 34 | Gru, GPU | - |
| lc-4 | report | comment on #218 + north star log | Gru | - |

## Ledger
| Task | Tier | Model | Harness | Session | Attempt | Tokens | Time | Result |
|---|---|---|---|---|---|---|---|---|

## Tether friction

## Progress log
- 2026-11-04 branch feat/bench-little-coder cut from main 8988cdb; log created.

## Next steps
- [ ] lc-1 research
- [ ] lc-2 runner
- [ ] lc-3 run
- [ ] lc-4 report
