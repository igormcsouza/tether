"""Runtime trace of a failing Python test: the calls into the code under test (#173).

When the same tests keep failing, the assertion shows only the final value. DebugRepair (Wu et al.,
2026, arXiv:2604.19305) shows intermediate runtime values to the model and fixes 51% more bugs
across 5 models; its rule-based instrumentation needs no model call. This module reruns one failing
test under `sys.settrace` inside the sandbox and lists each call into workspace code (arguments,
return value or exception), indented by depth.
"""

from __future__ import annotations

import re
import shlex

from tether.sandbox import SandboxPolicy

TRACE_LIMIT = 1500  # max chars of the trace, header included
TRACE_LINES = 30  # max call/return lines

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
    if code.co_name.startswith(("__", "<")) or code.co_filename.startswith("<"):
        return False
    path = os.path.abspath(code.co_filename)
    return path.startswith(root) and not (name.startswith("test") or "_test" in name)
lines, depth, skipped = [], [0], [0]
def tracer(frame, event, arg):
    code = frame.f_code
    if not ours(code):
        return None
    if event == "call":
        if len(lines) >= {TRACE_LINES}:
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
    lines.append(f"... {{skipped[0]}} more calls")
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


async def runtime_trace(sandbox: SandboxPolicy, test_id: str) -> str:
    """The trace of `test_id` as an observation note, or "" when nothing of ours ran."""
    _, out = await sandbox.execute_bash_with_code(f"python3 - {shlex.quote(test_id)}", _SCRIPT)
    body = out.strip()
    if not body or body.startswith("[exit") or "Traceback" in body:
        return ""
    name = test_id.rsplit(".", 1)[-1]
    header = f"\n[runtime trace of {name}: calls into your code, arguments and results]\n"
    return (header + body)[:TRACE_LIMIT]
