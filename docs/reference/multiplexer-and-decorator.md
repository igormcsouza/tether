# Multiplexer and Decorator

*For: people writing their own tools or debugging why a command was or was not understood. After this page you know how `act(cmd, stdin)` is parsed, which mistakes are repaired for the model and how `@tool` turns a Python function into a command.*

The multiplexer is the single door between the model and everything it can do. It splits `cmd` into a command and arguments, repairs trivial quirks, and answers a wrong call with a short usage hint instead of an error. The decorator builds the usage text from your function's type hints and docstring. Why there is only one action is in [One action for everything](../concepts/one-action-primitive.md); how to write a tool is in [Give the model a tool of your own](../guides/advanced/add-your-own-tool.md).

## `tether.multiplexer`

A command that is not enabled returns a self-healing error (`unknown_cmd`, no exception) listing the enabled tools and how to enable more (`--tools`, SDK `tools=[...]`, skill `tools:`). A known built-in that is merely disabled (`bash`, `web`, `edit`, `mem`, `skill`, `agent`) is reported as disabled, not unknown. The text lives in the error response (history), never in the system prompt prefix.

::: tether.multiplexer
    options:
      show_root_heading: false
      members_order: source

## `tether.decorator`

::: tether.decorator
    options:
      show_root_heading: false
      members_order: source
