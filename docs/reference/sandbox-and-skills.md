# Sandbox and Skills

*For: people deciding what a session may touch, and people packaging instructions and tools as skills. After this page you know the sandbox policy fields, what a skill file may contain and how each narrows or extends a session.*

The sandbox is a policy object (`SandboxPolicy`) that confines `bash` and `edit` to the workspace, hides secrets, scrubs the environment and can cut the network or set resource limits. Children (sub-agents, pipeline stages) can only narrow it. A skill is a Markdown file with front matter that bundles instructions, a default model, the tools it enables and its verify gates. For the practical side see [Security and sandbox](../guides/advanced/security-and-sandbox.md) and [Skills](../guides/basic/skills.md).

## `tether.sandbox`

::: tether.sandbox
    options:
      show_root_heading: false
      members_order: source

## `tether.skills`

::: tether.skills
    options:
      show_root_heading: false
      members_order: source

## `tether.retro`

::: tether.retro
    options:
      show_root_heading: false
      members_order: source
