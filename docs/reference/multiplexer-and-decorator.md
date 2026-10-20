# Multiplexer and Decorator

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
