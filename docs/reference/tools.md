# Built-in Tools

*For: people who need the exact syntax of a built-in tool. After this page you know every verb, flag and failure message of `done`, `bash`, `edit`, `web`, `mem` and `agent`.*

Only `done` is on by default; the rest are opted in with `--tools`, `Harness(tools=[...])` or a skill. Each section below is generated from the tool's docstring, which is also what the model sees when it runs `<tool> --help`. For examples of each in use, see [Built-in tools](../guides/basic/built-in-tools.md).

## `tether.tools.done`

::: tether.tools.done
    options:
      show_root_heading: false
      members_order: source

## `tether.tools.bash`

::: tether.tools.bash
    options:
      show_root_heading: false
      members_order: source

## `tether.tools.edit`

With `edit` enabled and `bash` not, a plain shell file write or read runs as `edit`: `echo ok > f`, `printf 'a\nb' > f` and `cat > f << 'EOF' ... EOF` as `edit write f`, `cat f` as `edit view f`, and `>> f` as `edit append f` (`echo -e` turns `\n` into a newline, `echo -n` adds none). `edit append <path>` adds `stdin` to the end of a file (created if missing); `edit write` replaces it. Other shell commands answer that the session has no shell, with a pointer to `edit` (and, with `web` on, `curl`/`wget` to `web fetch`); the model cannot enable a tool, so the message does not tell it how. A disabled built-in tool (`agent`, `mem`) still names the flags that enable it.

::: tether.tools.edit
    options:
      show_root_heading: false
      members_order: source

## `tether.tools.web`

::: tether.tools.web
    options:
      show_root_heading: false
      members_order: source

## `tether.tools.mem`

::: tether.tools.mem
    options:
      show_root_heading: false
      members_order: source

## `tether.tools.agent`

::: tether.tools.agent
    options:
      show_root_heading: false
      members_order: source
