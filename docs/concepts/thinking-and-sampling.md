# Thinking and sampling

*For: anyone running a model with a "thinking" mode (such as `qwen3.5`). After this page you know why tether bounds thinking, why it does not set a temperature, and what that did to wasted time.*

## The problem

Thinking models write their reasoning before the answer, and the reasoning counts against the same window as everything else. Sometimes a model keeps going and never stops: it thinks until the window is full, the server cuts it off, and the turn contains no command at all. We measured it in 68 full Polyglot runs of `qwen3.5:9b`: 53 turns with no action, 45 of them ending with prompt plus reply just over the 8,192-token window. Each cost 85 to 110 seconds, and in the runs that hit the 10-minute cap, 41% of the model's time was spent on such empty turns. Those runs were not slow at the work; they were stuck thinking.

## What we tried

| Idea | Result |
|---|---|
| Turn thinking off for every request | Pass count flat or lower; thinking is what lets the model solve the harder tasks |
| Retry when a turn is cut with no command | Cut empty turns from 3,672 s to 332 s of model time, but 20 turns still ran past 2,500 tokens: thinking is slow even when it fits, and the pass rate did not move |
| A bigger window (16k at the time) | Higher mean score but more runs killed by the time limit: slower per step |
| **Drop the forced temperature of 0.2** | Overflow turns fell by half (12.3% to 5.4%); pass count flat |
| **Bound the thinking per turn, re-ask once with thinking off** | Empty turns from 26 to 1 in 16 runs, model time lost from 33% to 16% |

## What tether does

- **Leave sampling to the model.** Tether sets no temperature or top-p. A forced `0.2` doubled the runaway-thinking rate on `qwen3.5:9b`, whose own defaults are tuned for its thinking mode. You can still set any parameter yourself (`--param temperature=0`, or in `providers.yaml`).
- **Give a thinking turn a budget.** On Ollama, a turn is streamed and may think for up to 2,048 tokens before its reply starts; the reply itself is limited only by a safety ceiling of 5,120 tokens for thinking and reply together (2,048 + 3,072, above every healthy turn we measured), and that ceiling caps every Ollama turn, thinking off or the retry included, unless you set `num_predict` yourself. If it thinks past the budget with no reply, or is cut with a half-written tool call that Ollama rejects, tether asks once more with thinking turned off. A tool call cut by the ceiling counts all 5,120 tokens (Ollama does not stream tool-call tokens, so that is what it used). If fewer than about 3,000 tokens of the window are free, thinking is off from the start.
- **Keep the thinking for you.** It is stored, visible with `tether read <id> --thinking`, and never sent back to the model.

## What we got

On 16 runs of the same eight exercises, the arm with bounded thinking (plus the sampling change and the failing-test source) passed 6, against 4 for the arm without it. That is inside the noise of 16 runs. The change that showed up clearly is the one it was built for: empty turns fell from 26 to 1, and time lost to them fell by half. Time the model used to waste on nothing now goes to attempts.

## What it costs

A thinking cap can cut a genuinely long reasoning step short. The one re-ask without thinking is the safety net; if you know a task needs long reasoning, set the budget yourself (`--param num_predict=-1`).

The budget caps only the thinking part, so a whole-file write after normal thinking (about 1 to 1.5k tokens) is no longer thrown away and redone ([AD-29](../architecture/decisions.md)). The cost is a streaming parse in the Ollama provider.

## References

- Decisions: [AD-28, AD-29](../architecture/decisions.md#e-providers). Reference: [providers](../reference/providers.md).
