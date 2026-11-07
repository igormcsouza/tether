"""Runtime trace of a failing Python test: the calls into the code under test (#173).

When the same tests keep failing, the assertion shows only the final value. DebugRepair (Wu et al.,
2026, arXiv:2604.19305) shows intermediate runtime values to the model and fixes 51% more bugs
across 5 models; its rule-based instrumentation needs no model call. This module reruns one failing
test under `sys.settrace` inside the sandbox and lists each call into workspace code (arguments,
return value or exception), indented by depth.
"""

from __future__ import annotations

import ast
import re
import shlex
from pathlib import Path

from tether.sandbox import SandboxPolicy

TRACE_LIMIT = 1500  # max chars of the trace, header included
TRACE_LINES = 30  # max call/return lines
TRACE_DEPTH = 2  # calls deeper than this (recursive helpers) are counted, not listed
NEAR_PASS = 3  # a run failing at most this many tests after a change is traced too
# Special methods that are construction, comparison or display, not behaviour (`__iter__`,
# `__next__`, `__enter__`, `__exit__` and the like are listed)
_NOISE = {
    "__init__", "__new__", "__del__", "__repr__", "__str__", "__format__", "__hash__", "__dict__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__", "__bool__", "__len__",
    "__getattr__", "__getattribute__", "__setattr__", "__delattr__", "__init_subclass__",
}  # fmt: skip

_UNITTEST = re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.M)
_PYTEST = re.compile(r"^FAILED ([\w/.-]+)\.py::(\w+)(?:::(\w+))?", re.M)

# Runs in the workspace as `python3 - <test id>`; prints the trace lines.
_SCRIPT = f"""
import os, reprlib, sys, unittest
target, root = sys.argv[1], os.getcwd()
sys.path.insert(0, root)
class Rep(reprlib.Repr):
    def repr_instance(self, x, level):
        text = super().repr_instance(x, level)
        if " object at 0x" not in text:
            return text
        try:
            fields_of = vars(x)
            assert isinstance(fields_of, dict)
        except Exception:
            return self.repr_str(str(x), level)
        if level <= 0:
            return f"{{type(x).__name__}}(...)"
        items = list(fields_of.items())[:4]
        fields = ", ".join(f"{{k}}={{self.repr1(v, level - 1)}}" for k, v in items)
        return f"{{type(x).__name__}}({{fields}})"
rep = Rep()
rep.maxstring = rep.maxother = 60
rep.maxlist = rep.maxdict = 4
rep.maxlevel = 3
def show(v):
    try:
        return rep.repr(v)[:120]
    except Exception:
        return "?"
def ours(code):
    name = os.path.basename(code.co_filename)
    if code.co_name in NOISE or code.co_name.startswith("<") or code.co_filename.startswith("<"):
        return False
    path = os.path.abspath(code.co_filename)
    return path.startswith(root) and not (name.startswith("test") or "_test" in name)
NOISE = {sorted(_NOISE)!r}
lines, depth, skipped = [], [0], [0]
def tracer(frame, event, arg):
    code = frame.f_code
    if not ours(code):
        return None
    if event == "call":
        if len(lines) >= {TRACE_LINES} or depth[0] >= {TRACE_DEPTH}:
            skipped[0] += 1
            return None
        names = code.co_varnames[: code.co_argcount + code.co_kwonlyargcount]
        args = ", ".join(f"{{n}}={{show(frame.f_locals[n])}}" for n in names if n in frame.f_locals)
        lines.append("  " * depth[0] + f"{{code.co_name}}({{args}})")
        depth[0] += 1
    elif event == "exception" and len(lines) < {TRACE_LINES}:
        lines.append("  " * depth[0] + f"raised {{arg[0].__name__}}: {{str(arg[1])[:80]}}")
    elif event == "return":
        depth[0] -= 1
        if len(lines) < {TRACE_LINES}:
            lines.append("  " * depth[0] + f"-> {{show(arg)}}")
    return tracer
try:
    suite = unittest.defaultTestLoader.loadTestsFromName(target)
except Exception:
    sys.exit(0)
sys.settrace(tracer)
suite.run(unittest.TestResult())
sys.settrace(None)
if skipped[0]:
    lines.append(f"... {{skipped[0]}} deeper or later calls not shown")
print("\\n".join(lines))
"""


def failing_test_id(out: str) -> str | None:
    """Dotted id (`module.Class.test`) of the first failing test in unittest or pytest output."""
    if m := _UNITTEST.search(out):
        name, where = m.groups()
        return where if where.endswith(f".{name}") else f"{where}.{name}"
    if m := _PYTEST.search(out):
        path, first, second = m.groups()
        return ".".join([path.replace("/", "."), first, *([second] if second else [])])
    return None


def smallest_failing(test_id: str, names: frozenset[str], root: Path) -> str:
    """`test_id` re-pointed at the failing test with the shortest source in the same test file.

    The smallest failing test gives the shortest trace (DebugRepair's test purification). Falls back
    to `test_id` when the file cannot be read or holds none of `names`.
    """
    module, _, _ = test_id.rpartition(".")
    path = root / (module.rpartition(".")[0].replace(".", "/") + ".py")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return test_id
    sizes = [
        ((node.end_lineno or node.lineno) - node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    return f"{module}.{min(sizes)[1]}" if sizes else test_id


async def runtime_trace(sandbox: SandboxPolicy, test_id: str) -> str:
    """The trace of `test_id` as an observation note, or "" when nothing of ours ran."""
    _, out = await sandbox.execute_bash_with_code(f"python3 - {shlex.quote(test_id)}", _SCRIPT)
    body = out.strip()
    if not body or body.startswith("[exit") or "Traceback" in body:
        return ""
    name = test_id.rsplit(".", 1)[-1]
    header = f"\n[runtime trace of {name}: calls into your code, arguments and results]\n"
    return (header + body)[:TRACE_LIMIT]
