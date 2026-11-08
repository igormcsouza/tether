# Run a session on its own branch

*For: people and orchestrators running several tether sessions at once. After this page you can give each run its own branch, read where its work went, and merge or remove it.*

This guide is for people, and for orchestrators that start several `tether` sessions at once. `tether run --worktree` gives each session its own git worktree and branch, so parallel runs cannot overwrite each other's files, and the result is a normal commit you can review and merge.

## Why

By default a run edits the directory you started it in, so two runs in the same checkout will collide. With `--worktree`, each run:

- gets a new worktree under `~/.cache/tether/worktrees/` on the branch `tether/<id>`;
- edits only that worktree;
- commits its changes on that branch when it stops, if anything changed.

Your own checkout is left alone until you decide to merge.

## The flags

| Flag | Meaning |
|------|---------|
| `--worktree` | Run in a git worktree on branch `tether/<id>`; the run commits its changes there when it stops |
| `--worktree-from` | Base ref for `--worktree` (default HEAD) |
| `--setup` | Shell command run in the worktree before the model starts; runs outside the sandbox, not offered over MCP |

`--worktree` must be started inside a git repository and needs `git` on PATH. Otherwise the run exits with a usage error and does not start.

## Example

```bash
tether run --worktree --setup "uv sync" --verify "uv run pytest -q" "fix the failing test"
```

This creates a worktree, installs dependencies with `uv sync`, lets the model work, runs the verify gate before `done`, and commits the result on `tether/<id>`. Add `--headless` to start it in the background and get the session id back.

## Read the branch and commit

The session record tells you where the work went:

```bash
tether status <id> --json
```

The relevant part of the output looks like this:

```json
{"id": "a1b2c3", "status": "done", "worktree": "/home/you/.cache/tether/worktrees/a1b2c3", "branch": "tether/a1b2c3", "commit": "9f3e2d1c0b7a6e5f4d3c2b1a0987654321fedcba"}
```

The session JSON holds `worktree` (the path), `branch` (`tether/<id>`), and `commit` (the full sha, or `null` when the run changed nothing). The commit uses `git add -A`, so it commits everything not ignored by .gitignore.

## Merge the branch

Review the commit, then merge it like any other branch:

```bash
git log tether/<id>
git merge tether/<id>
```

Or cherry-pick the commit with `git cherry-pick <commit>`.

## Clean up

When you are done with a session, remove its worktree and branch:

```bash
git worktree remove <path>
git branch -D tether/<id>
```

Use `<path>` from the `worktree` field. Delete the branch only after its commit is merged or you no longer need it.

## Setup runs outside the sandbox

`--setup` is a shell command that runs on the host, outside the model sandbox, before the model starts. Treat it as code you trust. It is not offered over MCP: an MCP caller can create a worktree but cannot supply a setup command.

## When it goes wrong

- **`needs a git repository` and exit code 1.** The run was started outside a git checkout, or `git` is not on PATH. Change into the repository and run again.
- **`git worktree add failed`.** The `--worktree-from` ref does not exist, or the branch `tether/<id>` is already taken. Check the ref with `git rev-parse <ref>`.
- **`--setup` timed out or failed.** The setup command ran on the host and did not finish. Run it by hand in the worktree path from the `worktree` field to see the error.
- **`commit` is `null`.** The run changed nothing, so there is no commit to merge. Read the result text to see what it concluded.
