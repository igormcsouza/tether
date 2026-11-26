# The repair loop around tests

*For: anyone who wants to know what tether adds around a failing test and why. After this page you know the five notes tether can append to a test result, what research each comes from, and what each did when we measured it.*

## The problem

Most of a small model's time goes into typing code. A whole-file rewrite of a 100-line module costs `qwen3.5:9b` 30 to 100 seconds; running the tests takes under one. And a Python test failure is a poor message: the traceback shows the failing line (`assertEqual(total(basket), 10240)`) but not the inputs set up three lines above it, so the model guesses or re-reads the whole test file. Worse, an edit that fixes one test often breaks another that passed, and nothing in `FAILED (failures=3)` says that.

## What the research says

- Repair is limited by **feedback quality**, not the number of tries (Olausson et al., ICLR 2024).
- Showing the **runtime values** behind a failure improves repair (Zhong et al., LDB, ACL 2024).
- Iterative repair often **breaks code that worked**: 40% to 73% of multi-turn tasks lose behaviour that was correct earlier, and checking each new version against the earlier tests is the one mitigation that helped every model (Huang et al., ASE 2026). Repeated fixing also falls into add-and-remove cycles (Wang-Lin et al., 2026).
- Running the tests automatically after each edit is what Aider's auto-test does, and AlphaCodium's flow builds on tests too.

## What tether does

All of it is the harness's time, not the model's. No model call, no addition to the fixed prompt.

**Tests after every edit (`[auto-test]`).** Once the model has run a recognised test command (a runner name outside quotes and heredocs), tether re-runs it after every command that writes an existing file and appends the result. The model sees whether a version works before it types the next one.

**The failing test's source (`[failing test source]`).** When a test fails, tether appends the source of up to three failing test functions named in the traceback (at most 1,500 characters), so the model sees the inputs:

```text
[failing test source]
# book_store_test.py:12
    def test_four_groups_of_four(self):
        basket = [1, 1, 2, 2, 3, 3, 4, 5, 1, 1, 2, 2, 3, 3, 4, 5]
        self.assertEqual(total(basket), 10240)
```

**Where a missing name really is (`[hint]`).** When any command fails with `cannot import name 'X' from 'm'` or `module 'm' has no attribute 'X'` and `m.py` is a workspace file, tether looks `X` up in it. If `X` sits inside a class or a function, one line says so; if it is nowhere, one line says the file has no top-level `X`:

```text
[hint] `WHITE` is defined inside `class Board` in go_counting.py, not at module level, so importing it from `go_counting` fails. Define it at the top level of the file.
```

**A named regression (`[regression]`).** Tether remembers which tests failed on the last run of the same suite. If tests that passed then fail now, one line says which:

```text
[regression] Your last change broke 1 test(s) that passed before: test_o_wins; now passing: test_x_wins. Keep what worked.
```

**A runtime trace.** When the same tests fail again after a change, or only a few still fail, tether runs the smallest failing test under a tracer and appends the calls into your code with arguments and results (two levels deep, at most 30 lines):

```text
[runtime trace of test_f: calls into your code, arguments and results]
test_f(self=<m_checks.T testMethod=test_f>)
  f()
  -> 1
  raised AssertionError: 1 != 3
```

**A rewrite that changed nothing.** If a write leaves the code identical (the same bytes, or the same syntax tree for Python, so a changed comment does not count), one line says so. In one run of eight exercises, 9 of 62 rewrites were like this:

```text
[NUDGE] hangman.py: only comments or spacing changed, the code is the same. The tests will fail the same way; change the logic.
```

A whole-file rewrite of 20 or more lines that changed a fifth of them or less is pointed to `edit replace` once per file. A `bash` command that leaves a Python file unparsable is undone, with one `[REVERTED]` line.

## What we measured

All numbers are `qwen3.5:9b` on Polyglot exercises, small samples, reported as we saw them.

| Change | What moved | Pass rate |
|---|---|---|
| The whole loop, on one hard exercise (`paasio`, 5 runs, 600 s cap) | mean score 0.63 over 3 runs to 0.94 over 5 runs | 1 of 5 passed; the rest ended at the time cap with 22 to 24 of 25 tests passing |
| Failing test source (16 runs) | Re-reads of the test file after a failure 25% to 17% | 4 of 16 both ways |
| Regression line (16 runs) | Edits that fix one test and break another 40% to 15% | 6 of 16 both ways |
| Everything with the 32k context (full 34 x 2, v0.2.18) | Mean score 0.756 to 0.830 | 40 of 68 to 45 of 68: the first change whose gain cleared the noise |

So: each note changed the behaviour it was built to change, and the pass rate moved when they arrived together and with a larger window. We cannot attribute the gain to one note.

## What it costs

Test re-runs cost wall time on slow suites, and a tracer adds a few seconds. Each note is bounded in size, has a test, and appears only when it applies.

## References

- Olausson, T. X., et al. (2024). *Is Self-Repair a Silver Bullet for Code Generation?* ICLR 2024. [arXiv:2306.09896](https://arxiv.org/abs/2306.09896)
- Zhong, L., Wang, Z., & Shang, J. (2024). *Debug like a Human: A Large Language Model Debugger via Verifying Runtime Execution Step-by-step (LDB).* ACL Findings 2024. [arXiv:2402.16906](https://arxiv.org/abs/2402.16906)
- Huang, Y., et al. (2026). *Regression Accumulation in Multi-Turn LLM Programming Conversations.* ASE 2026. [arXiv:2607.01855](https://arxiv.org/abs/2607.01855)
- Wang-Lin, X., Isopoussu, A., & Mahon, L. (2026). *If It's Not Buggy, Don't Fix It: On the Dynamics of Iterative Bug-fixing with LLMs.* [arXiv:2609.10123](https://arxiv.org/abs/2609.10123)
- Decisions: [AD-24](../architecture/decisions.md#d-the-loop).
