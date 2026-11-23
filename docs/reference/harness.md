# Harness and CLI

*For: people embedding tether in Python or reading the control loop. After this page you know which class starts a session, which parameters it takes and where the CLI maps onto them.*

`Harness` is the control plane: it owns the loop that assembles the prompt, asks the model, runs one command, records it and decides whether to stop. Everything the CLI does (`tether run`, `send`, `wait`, `pipeline`) is a thin wrapper over a method here, so a Python program can do the same with `await Harness(...).run(goal)`. For a walk-through with examples see [Python SDK and custom tools](../guides/advanced/sdk-and-custom-tools.md); for what each stop condition means see [the deterministic envelope](../concepts/deterministic-envelope.md).

## `tether.harness`

::: tether.harness
    options:
      show_root_heading: false
      members_order: source

## `tether.cli`

::: tether.cli
    options:
      show_root_heading: false
      members_order: source

## `tether.pipeline`

::: tether.pipeline
    options:
      show_root_heading: false
      members_order: source
