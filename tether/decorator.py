"""@tool decorator introspection and ultra-compact JIT --help synthesis."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin, get_type_hints


@dataclass(slots=True)
class ParamSpec:
    name: str
    flag: str
    type_name: str
    annotation: Any
    required: bool
    default: Any
    is_variadic: bool = False


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., Any]
    params: list[ParamSpec]
    accepts_stdin: bool
    is_async: bool
    custom_help: str | None = None
    raw_dispatch: bool = False  # If True, passes (args: list[str], stdin: str | None) directly

    def index_line(self) -> str:
        """Return a 1-line summary (strictly <= 12 tokens) for the static system prompt."""
        short_desc = " ".join(self.description.strip().split())
        line = f"- {self.name}: {short_desc}"
        if len(line) > 44:
            line = line[:41].rstrip() + "..."
        return line

    def help_text(self) -> str:
        """Return ultra-compact --help output (target <= 60 tokens)."""
        if self.custom_help:
            return self.custom_help.strip()

        parts: list[str] = [self.name]
        for p in self.params:
            if p.is_variadic:
                parts.append(f"<{p.name}...>")
            elif p.required:
                parts.append(f"<{p.name}:{p.type_name}>")
            else:
                default_repr = repr(p.default) if isinstance(p.default, str) else str(p.default)
                parts.append(f"[{p.flag} {p.type_name}={default_repr}]")
        if self.accepts_stdin:
            parts.append("[stdin]")

        usage_line = " ".join(parts)
        doc = (inspect.getdoc(self.fn) or self.description).strip().splitlines()[0]
        if len(doc) > 100:
            doc = doc[:97] + "..."
        return f"Usage: {usage_line}\nDesc : {doc}"

    async def invoke(self, args: list[str], stdin: str | None = None) -> str:
        """Parse CLI arguments against ParamSpecs and invoke the underlying function."""
        if self.raw_dispatch:
            res = self.fn(args, stdin)
            if inspect.isawaitable(res):
                res = await res
            return str(res) if res is not None else ""

        if any(a in ("--help", "-h") for a in args):
            return self.help_text()

        parsed_kwargs = self._parse_args(args, stdin)
        if isinstance(parsed_kwargs, str):
            # Validation error string with self-healing --help
            return f"Error: {parsed_kwargs}\n{self.help_text()}"

        # Params before `*args` must be passed positionally (Python rejects them as keywords).
        call_args: list[Any] = []
        var = next((p for p in self.params if p.is_variadic), None)
        if var:
            for p in self.params[: self.params.index(var)]:
                call_args.append(parsed_kwargs.pop(p.name))
            words = parsed_kwargs.pop(var.name)
            call_args += [words] if isinstance(words, str) else words
        res = self.fn(*call_args, **parsed_kwargs)
        if inspect.isawaitable(res):
            res = await res
        return str(res) if res is not None else ""

    def _parse_args(self, args: list[str], stdin: str | None) -> dict[str, Any] | str:
        param_by_flag = {p.flag: p for p in self.params}
        param_by_name = {p.name: p for p in self.params}
        values: dict[str, Any] = {}
        positionals: list[str] = []

        i = 0
        while i < len(args):
            tok = args[i]
            if tok.startswith("--"):
                if "=" in tok:
                    flag, raw_val = tok.split("=", 1)
                else:
                    flag = tok
                    raw_val = None
                p = param_by_flag.get(flag) or param_by_name.get(flag.lstrip("-").replace("-", "_"))
                if not p:
                    return f"unknown flag `{flag}`."
                if p.type_name == "bool" and raw_val is None:
                    if i + 1 < len(args) and args[i + 1].lower() in ("true", "false", "1", "0"):
                        raw_val = args[i + 1]
                        i += 1
                    else:
                        values[p.name] = True
                        i += 1
                        continue
                elif raw_val is None:
                    if i + 1 >= len(args):
                        return f"flag `{flag}` requires a value."
                    raw_val = args[i + 1]
                    i += 1
                converted = _coerce_value(raw_val, p)
                if isinstance(converted, tuple):
                    return str(converted[1])
                values[p.name] = converted
            else:
                positionals.append(tok)
            i += 1

        # Map remaining positional arguments in order. The last unfilled non-variadic `str`
        # param swallows extra unquoted words (minus those reserved for later required params).
        unfilled = [p for p in self.params if p.name not in values]
        greedy = None
        if not any(p.is_variadic for p in unfilled):
            greedy = next((p for p in reversed(unfilled) if p.type_name == "str"), None)
        pos_idx = 0
        past_greedy = False
        for n, p in enumerate(unfilled):
            past_greedy = past_greedy or p is greedy
            if p.is_variadic:
                values[p.name] = positionals[pos_idx:]
                pos_idx = len(positionals)
            elif p is greedy and pos_idx < len(positionals):
                reserve = sum(1 for q in unfilled[n + 1 :] if q.required)
                end = max(len(positionals) - reserve, pos_idx + 1)
                values[p.name] = " ".join(positionals[pos_idx:end])
                pos_idx = end
            elif pos_idx < len(positionals) and not (past_greedy and not p.required):
                converted = _coerce_value(positionals[pos_idx], p)
                if isinstance(converted, tuple):
                    return str(converted[1])
                values[p.name] = converted
                pos_idx += 1
            elif not p.required:
                values[p.name] = p.default
            elif stdin is not None and len(self.params) == 1 and p.type_name == "str":
                # Allow single required string param to be satisfied via stdin
                values[p.name] = stdin
                stdin = None
            else:
                return f"missing required argument `<{p.name}:{p.type_name}>`."

        if pos_idx < len(positionals):
            return f"unexpected positional arguments: {' '.join(positionals[pos_idx:])}"

        if self.accepts_stdin:
            values["stdin"] = stdin

        return values


def _type_label(ann: Any) -> str:
    origin = get_origin(ann)
    if origin is Literal:
        choices = "|".join(str(a) for a in get_args(ann))
        return choices
    if ann is int:
        return "int"
    if ann is float:
        return "float"
    if ann is bool:
        return "bool"
    return "str"


def _coerce_value(raw: str, p: ParamSpec) -> Any | tuple[Literal["err"], str]:
    origin = get_origin(p.annotation)
    if origin is Literal:
        allowed = [str(a) for a in get_args(p.annotation)]
        if raw not in allowed:
            return ("err", f"`{p.name}` must be one of {'|'.join(allowed)} (got `{raw}`).")
        return raw
    if p.annotation is int:
        try:
            return int(raw)
        except ValueError:
            return ("err", f"`{p.name}` expects int (got `{raw}`).")
    if p.annotation is float:
        try:
            return float(raw)
        except ValueError:
            return ("err", f"`{p.name}` expects float (got `{raw}`).")
    if p.annotation is bool:
        low = raw.lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
        return ("err", f"`{p.name}` expects bool (got `{raw}`).")
    return raw


def build_tool_spec(
    fn: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    custom_help: str | None = None,
    raw_dispatch: bool = False,
) -> ToolSpec:
    """Introspect a Python function into a ToolSpec."""
    tool_name = (name or fn.__name__).strip().replace("_", "-")
    doc = inspect.getdoc(fn) or ""
    first_line = doc.splitlines()[0].strip() if doc else f"Run {tool_name}"
    tool_desc = description or first_line

    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    params: list[ParamSpec] = []
    accepts_stdin = False

    if not raw_dispatch:
        for param_name, param in sig.parameters.items():
            if param_name == "stdin":
                accepts_stdin = True
                continue
            ann = hints.get(param_name, param.annotation)
            if ann is inspect.Parameter.empty:
                ann = str
            is_var = param.kind == inspect.Parameter.VAR_POSITIONAL
            required = param.default is inspect.Parameter.empty and not is_var
            default_val = None if required else param.default
            flag = f"--{param_name.replace('_', '-')}"
            params.append(
                ParamSpec(
                    name=param_name,
                    flag=flag,
                    type_name=_type_label(ann),
                    annotation=ann,
                    required=required,
                    default=default_val,
                    is_variadic=is_var,
                )
            )

    spec = ToolSpec(
        name=tool_name,
        description=tool_desc,
        fn=fn,
        params=params,
        accepts_stdin=accepts_stdin,
        is_async=inspect.iscoroutinefunction(fn),
        custom_help=custom_help,
        raw_dispatch=raw_dispatch,
    )
    setattr(fn, "__tether_tool__", spec)  # noqa: B010
    return spec


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    namespace: str | None = None,
    description: str | None = None,
) -> Any:
    """Decorator to register a sync or async Python function as a Tether virtual CLI tool."""
    effective_name = name or namespace

    def decorator(target: Callable[..., Any | Awaitable[Any]]) -> Callable[..., Any]:
        build_tool_spec(target, name=effective_name, description=description)
        return target

    if fn is not None:
        return decorator(fn)
    return decorator
