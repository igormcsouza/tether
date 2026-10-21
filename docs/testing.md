# Testing: golden traces

Tether is a deterministic envelope around a random model, so a change to framing, folding,
nudges, tools or retries can silently change what the model is shown. Golden traces make that
visible without a model, a network or any judgment.

Each `tests/golden/<name>.json` is a scripted session: workspace files, stubbed network
tools, the model's recorded steps and optional `send` phases. `tests/test_golden.py` replays
it through the **real** harness, multiplexer, `edit`/`done`/`mem` tools, context assembly and
folding, and compares everything against `<name>.snap.json`: the exact messages sent at every
step, event types, token estimates, final status/result and final workspace files.

- A PR that changes nothing the model sees keeps every snapshot green. A PR that does shows a
  JSON diff to approve or reject in review.
- Intended change: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`, then review the diff.
- Record a real run: `python scripts/record_golden.py <db> <session_id> tests/golden/<name>.json --stub web`
  (trim or sanitise third-party text first).

Shipped traces: a real researcher run (web stubbed, plain-text `done` nudges), a synthetic
coding run covering the edit failure modes seen with small models, and a `done --ask` /
`send` resume. Add one for every behaviour that must not regress.
