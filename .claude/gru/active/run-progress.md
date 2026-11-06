# Run progress feedback (--verbose + activity dots)
- Slug: run-progress
- Status: active
- Started: 2026-11-06   Updated: 2026-11-06   Closed: —
- Branches / PRs: claude/tether-local-setup-error-6fb430
- Budget: warn 300k / stop 400k paid tokens

## Goal
Foreground `tether "<goal>"` is silent while the model loads/thinks. Add `--verbose` (one stderr line per step) and an always-on animated dots indicator (stderr, TTY only). Document both.

## Requests
- 2026-11-06 PO: feedback on model loaded / waiting; --verbose if missing; always-visible three-dots indicator even without verbose; docs.

## Decisions
- No `--verbose` exists today (grep cli.py: none). Plan: new tether/progress.py polling SQLite turns, no harness change.

## Plan (task cards)
see PO preview

## Ledger
| Task | Tier | Model | Harness | Session | Attempt | Tokens | Time | Result |
|---|---|---|---|---|---|---|---|---|

## Progress log
- 2026-11-06 plan drafted, waiting for PO accept
- 2026-11-06 T1 tests committed 0619c04. T2 attempt 1 tether MCP nemotron ses_c5e4e75b: FAILED max_steps; MCP workspace is main checkout /home/walkdead/Projects/tether, not worktree; wrote progress.py there. Salvaged into worktree, removed stray files from main.
## Tether friction
- tether_run MCP always roots in main repo checkout, ignores the session worktree; minion burned 15 steps looking for a test file that was only in the worktree (ses_c5e4e75b).
- 2026-11-06 T2 finished by gru (PO-informed: MCP cannot reach worktree, 12-line edit). T3 docs, T4 e2e done. unit 528 pass 100% cov, e2e 85 pass (409s), real TTY run OK. PR opened.
