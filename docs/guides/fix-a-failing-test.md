# Fix a failing test with a local model

*For: developers with a small local model and a red test. After this page you can hand the fix to tether, let a verification gate decide when it is done, and read back what it did.*

You have a function with a bug and a test that shows it. You would rather not spend frontier-model tokens on a one-line fix, so you point tether at a 9B model running on your own machine and let a **verification gate** decide whether the job is done.

## The situation

`prices.py` applies a tax rate, but multiplies by the rate instead of adding it:

```python
def total_with_tax(prices, rate):
    """Sum of prices with a tax rate applied (rate 0.2 = 20%)."""
    return sum(prices) * rate
```

`python3 -m unittest -q` fails: `6.0 != 36.0`.

## Hand it over

```bash
tether run --model ollama/qwen3.5:9b --tools bash,edit \
    --verify "python3 -m unittest -q" \
    "The tests in test_prices.py fail. Fix prices.py so they pass. Do not edit the tests."
```

- `--tools bash,edit` is the only thing the model may use besides `done`. Tether loads nothing else, so the prompt stays small.
- `--verify` is the part that matters: a command tether runs itself, inside the sandbox, before it accepts `done`. If it fails, the model gets the output and keeps working. The model cannot declare victory on its own say-so.

The run printed this and exited with code `0` after 31 seconds:

```text
Finished by the harness: the model stopped calling tools after its change and every verification gate passes.
```

## What it did

`tether read <id> --steps` shows the model's commands (trimmed):

```text
[step 1] act('cat test_prices.py')
[step 2] act('cat prices.py')
[step 3] act('echo "def total_with_tax(prices, rate): ... return sum(prices) * (1 + rate)" > prices.py')
[step 6] act('bash python3 test_prices.py')      # tests: OK
```

It read the test, read the code, rewrote the function, and ran the tests. `prices.py` now ends with `return sum(prices) * (1 + rate)`.

Small models sometimes fix the problem and then keep re-running the check without calling `done`. That is why the last line says *Finished by the harness*: tether noticed the work was verified and closed the session as `COMPLETED` instead of letting it look like a failure.

## Look at what it cost

```bash
tether stats
```

prints, per model, how many sessions passed, the average steps and tokens, and where the friction was (commands it got wrong, loops it was stopped from). On this task the model first tried `python` (not installed in the sandbox) and `tether` answered with the commands that do exist, so it corrected itself within three steps.

## When it goes wrong

- **`FAILED: Stalled`, exit code 4.** The model repeated itself and no gate passed. Run `tether read <id> --steps` to see the loop, name the file and the edit in the goal, or use a stronger model.
- **`FAILED: Verification gate ... misconfigured`.** The gate command itself is broken (command not found, sandbox refused it). Run the gate by hand first.
- **Not sure the gate is strict enough?** A gate that exits `0` when its input is missing checks nothing. Make it fail when the file or test is absent.

More: [Troubleshooting](../troubleshooting.md), [gates](../tutorial/workflows-and-telemetry.md#gates), [CLI reference](../reference/cli.md).
