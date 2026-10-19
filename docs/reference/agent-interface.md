# Agent Interface Reference

Machine-readable surface for calling Tether from another agent. Code: `tether/api.py`, `tether/mcp.py`, `tether/schema.py`.

## Session JSON (schema version 1)

```json
{"v": 1, "id": "ses_…", "status": "COMPLETED|WAITING_INPUT|FAILED|RUNNING|PENDING",
 "model": "ollama/qwen3.5:9b", "steps": 4, "max_steps": 15,
 "tokens": {"prompt": 1200, "completion": 90}, "duration_ms": 8100,
 "failure": null, "exit_code": 0, "result": "…"}
```

- `result` is the deliverable, or the pending question when `WAITING_INPUT`. It is `null` on failure.
- `failure` is `{"kind": "gate|max_steps|worker_error", "gate": "<cmd>|output-schema|null", "message": "…"}`.
- Keys are stable; new keys may be added.

`--json` is available on `run`, `pipeline`, `status`, `list`, `read` (also `--digest`, `--steps`), `wait`, `send` and `stats`. With `--headless` it prints `{"v":1,"id":"ses_…"}`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | completed |
| 1 | usage error (bad flag, unknown session, invalid pipeline) |
| 2 | waiting for input (`done --ask`) |
| 3 | verification gate failed (including `--output-schema`) |
| 4 | max steps reached |
| 5 | worker or provider error |

In plain mode the failure reason goes to **stderr**; stdout only ever holds a deliverable. `wait` returns the highest code among its sessions.

## Other flags

- `tether run --result-file <path>`: write the deliverable to a file, print nothing on stdout.
- `tether run --output-schema <schema.json>`: `done` is rejected (like a failed gate, 0 prompt tokens until it fails) unless the deliverable is JSON matching the schema. Supported subset: `type`, `enum`, `required`, `properties`, `items`.
- `tether events <id> [--follow]`: one JSON object per turn (`turn`, `step`, `role`, `cmd`, `event`, `text`); with `--follow` streams until the session ends and finishes with `{"event":"status","status":"…"}`.

## MCP server: `tether mcp [--db <path>] [--workspace <dir>]`

Optional: `pip install "tether-sdk[mcp]"` (installs the official `mcp` SDK; core Tether never imports it). Without the extra, `tether mcp` prints a warning with the install command to stderr and exits 1. Transport: stdio, `tools` capability only. Tool results are the JSON above as text content; failures set `isError`.

| Tool | Arguments |
|------|-----------|
| `tether_run` | `goal`, `model`, `skill`, `tools`, `verify[]`, `max_steps`, `sandbox`, `no_network`, `output_schema`, `wait` (default true) |
| `tether_status` | `id` |
| `tether_wait` | `ids[]`, `timeout` |
| `tether_read` | `id`, `mode` = `full` \| `digest` \| `steps` |
| `tether_send` | `id`, `message`, `wait` (default false: resume in background) |
| `tether_list` | `limit` |
| `tether_stats` | `model`, `skill` |
| `tether_query` | `id`, `query`, `top` |

Security: sandboxes are always rooted at `--workspace` (default: the server's cwd). Callers can choose `read-only` or `no_network`, never widen.
