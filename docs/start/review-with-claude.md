# Let Claude call tether to review your writing

*For: people who work with Claude Code (or Codex, Cursor, Gemini CLI) and want it to hand routine work to a cheaper model. After this page you can connect tether to Claude in one command and ask Claude to use it while you write.*

You are writing a blog post and Claude is your editor. Claude is strong and costs real tokens, and a lot of an editor's day is mechanical: read the draft, list the typos, flag the claims that do not follow. Tether lets Claude send that reading to a different model and take back only a short answer.

## Connect it once

Install tether with its MCP extra, then register it with Claude Code. `--workspace` is the folder tether is allowed to touch.

```sh
uv tool install "tether-sdk[mcp]"
claude mcp add tether -- tether mcp --workspace "$PWD"
```

Nothing else to configure. Claude now has a `tether_run` tool (and `tether_status`, `tether_wait`, `tether_read`, `tether_send` for longer jobs). Other assistants take the same command in their MCP settings; see [Use tether inside your agent](../guides/advanced/use-from-your-agent-mcp.md).

## Tell Claude when to use it

Add two lines to the `CLAUDE.md` of your blog folder:

```markdown
When I ask for a review of a draft, call `tether_run` with
`model: "nvidia/nvidia/nemotron-3-ultra-550b-a55b"` and tools `["bash"]` to read it.
Report the findings in your own words and keep the final judgement for yourself.
```

## Ask Claude

Here is `draft.md`, with problems planted on purpose:

```markdown
# Why we moved our build to a monorepo

Last year we had 14 repositorys and every release was a mess. We moved everything into one repo in March and builds got 40% faster, which proves monorepos are always better. Our CI now takes 12 minutes. Before it took 20 minutes, so thats a 40% win.

The migration was easy: one engineer did it in a weekend. We dont recomend you do it without a plan though. Teh biggest problem was permissions, we ended up giving everyone write access to everything.

In conclusion, monorepos are the future and every team should switch.
```

You type to Claude: *"Review draft.md before I publish it."* Claude calls tether. What comes back to Claude is not a transcript of the other model thinking. It is this small object (the same JSON you get from `tether run --json` in a shell):

```json
{
  "v": 1,
  "id": "ses_09a5d090",
  "status": "COMPLETED",
  "model": "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
  "steps": 3,
  "tokens": { "prompt": 1845, "completion": 748 },
  "duration_ms": 13569,
  "failure": null,
  "exit_code": 0,
  "result": "**Logical Problems:**\n1. **Hasty generalization**: \"proves monorepos are always better\" extrapolates universal truth from one team's single migration.\n2. **Internal contradiction**: Calls migration \"easy\" (one engineer, one weekend) then warns against doing it without a plan—undermines the \"easy\" claim.\n3. **Overreaching conclusion**: \"Every team should switch\" ignores context (team size, codebase complexity, tooling maturity) and bases recommendation on n=1.\n\n**Typos:**\n- repositorys → repositories\n- thats → that's\n- dont → don't\n- recomend → recommend\n- Teh → The"
}
```

Thirteen seconds and about 2,600 tokens, none of them from Claude's own context. Claude reads the `result` and tells you what to fix.

Notice what the review did not catch: that "40% faster" does not match 20 minutes down to 12 (that is 40% *shorter*; "faster" would be 67%). A cheaper model is a reader, not a replacement for your own judgement, and that is why the rule above says Claude keeps the final call.

## Without MCP

Any assistant that can run a shell command can do the same. The exit code tells it what happened (`0` done, `2` needs input or stuck, `3` your check failed):

```sh
tether run --json --model nvidia/nvidia/nemotron-3-ultra-550b-a55b --tools bash \
  "Review draft.md as a blog editor: list the 3 most important logical problems and the typos. Do not edit the file. Keep it under 150 words."
```

## Where to go next

- [Delegate work from your agent](../guides/advanced/delegate-from-your-agent.md) goes further: failing tests, long jobs, answering questions the small model asks.
- [Write and check a script with Nemotron](script-with-nemotron.md) uses the same hosted model you just called.
