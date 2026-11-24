# Loops, stalls and fresh starts

*For: anyone who has watched a model repeat itself and wondered what tether does about it. After this page you know the stages tether goes through, and why starting fresh often beats fixing a wrong attempt.*

## The problem

Small models fall into loops. Some emit the exact same command twice. Some alternate between two or three commands for twenty steps. Some read one file over shifting line ranges (`sed -n 1,40p`, `sed -n 40,100p`, ...) and never edit. Others patch a wrong idea again and again, each patch a little different, the same test failing each time.

Nudging with different wording did not help: about fifteen variants of nudges and stall messages made no measurable difference on full runs. What helped was changing the situation, not the sentence.

## What the research says

*Is Self-Repair a Silver Bullet for Code Generation?* (Olausson et al., ICLR 2024) found that repair quality is limited by the quality of the feedback, and that for weaker models a fresh attempt is often better than repairing the previous one. A wrong design plus many patches loses to a clean start.

## What tether does

Stages, each deterministic and none costing a model call:

1. **Repeat.** The same command twice in a row is caught before it runs and answered with a nudge that says what to do instead. A repeat of a read of an unchanged file is answered with a pointer to the earlier output.
2. **Cycle.** A cycle of two commands repeated three times, or of three or four repeated twice, is skipped and named (`[CYCLE DETECTED]`). Seven reads of one file with no change in between count as a cycle too. A rewrite that gives a file an earlier content (a flip between two versions) is not progress, and a bare `echo` that only talks back counts as a stall, so both move the session towards the next stage.
3. **Wrap up.** After four warnings with no change, the model gets one turn to finish: a read-only session is asked for its final answer, one that already changed something is asked to call `done` with what is done and what is left, unless its checks already finish it.
4. **Restart.** If still stuck, or the same check command has failed three times with edits between, the session *restarts*: the history is replaced by one short message with the files as the model left them, the last failing output and what was tried. The model continues from there with a clean head. When the cause was a repeatedly failing check, the files the model changed go back to how they started, and the message names the failing tests, not the failed code.
5. **Hand back.** After two restarts, being stuck again ends the session `WAITING_INPUT` with a summary, so you can refine the task and `send` it.

An exception protects good work: if a version fails at most three tests and passes more than twice that many, tether keeps it. If three later attempts do not beat it, its files are put back in place with one `[RESTORED]` line, and the history stays.

## What we got

The restart and hand-back changes (v0.2.14) turned silent step-limit deaths into recoverable sessions. Stalls are the dominant way small models fail ("max steps without calling `done`", "wall clock"), so most of the benefit shows as sessions that end with something usable instead of nothing. On the effect on the pass rate, we have to be honest: individual stall changes were inside the noise of a 24-run benchmark, and we do not claim a number for them. See [benchmarks](../benchmarks/polyglot.md) for what moved the pass rate and what did not.

## What it costs

A restart throws away history, including some good reasoning. That is why it fires only after the earlier, cheaper stages did not help.

## References

- Olausson, T. X., et al. (2024). *Is Self-Repair a Silver Bullet for Code Generation?* ICLR 2024. [arXiv:2306.09896](https://arxiv.org/abs/2306.09896)
- Decisions: [AD-20, AD-21](../architecture/decisions.md#d-the-loop).
