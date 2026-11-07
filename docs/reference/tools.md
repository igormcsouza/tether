# Built-in Tools

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

With `edit` enabled and `bash` not, a plain shell file write or read runs as `edit`: `echo ok > f`, `printf 'a\nb' > f` and `cat > f << 'EOF' ... EOF` as `edit write f`, `cat f` as `edit view f`, and `>> f` as `edit append f`. `edit append <path>` adds `stdin` to the end of a file (created if missing); `edit write` replaces it. Other shell commands answer `unknown command` with a pointer to `edit`.

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
